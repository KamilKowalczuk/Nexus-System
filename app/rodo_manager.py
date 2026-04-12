# app/rodo_manager.py
"""
NEXUS COMPLIANCE ENGINE - Moduł Zgodności z GDPR (RODO) i PKE
Zaprojektowany dla modelu SaaS (Data Processor / Tenant Isolation).

UWAGA: Stopka biznesowa (KSH) jest pobierana z bazy danych (Client.html_footer).
       Ten moduł obsługuje wyłącznie klauzulę RODO + zarządzanie kryptograficzną
       czarną listą (EMAIL + DOMAIN).
"""

import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
from typing import Literal

from sqlalchemy.orm import Session

from app.database import Lead, OptOut

logger = logging.getLogger("nexus_compliance")

EntryType = Literal["EMAIL", "DOMAIN"]


# ---------------------------------------------------------------------------
# SZABLON RODO & OPT-OUT (DOKLEJANY NA SAMYM DOLE MAILA)
# ---------------------------------------------------------------------------

_RODO_CLAUSE_TEMPLATE = """\
<div style="margin-top: 15px; font-family: Arial, sans-serif; font-size: 10px; \
color: #888888; line-height: 1.3; border-top: 1px solid #eeeeee; padding-top: 10px;">
  Administratorem Twoich danych osobowych jest {client_name}. Przetwarzamy Twoje dane osobowe \
w zakresie: adres e-mail, imię, nazwisko, stanowisko służbowe oraz nazwa pracodawcy, \
które zostały pozyskane z publicznie dostępnych źródeł internetowych (m.in. strony www, \
rejestry branżowe, portale ogłoszeniowe). Kontaktujemy się z Tobą na podstawie naszego \
prawnie uzasadnionego interesu (art. 6 ust. 1 lit. f RODO), w celu zapytania o możliwość \
nawiązania relacji B2B. Pełne informacje o tym, jak przetwarzamy Twoje dane (w tym o prawie \
do sprzeciwu, usunięcia i dostępu), znajdziesz w naszej <a href="{privacy_policy_url}" \
style="color: #888888; text-decoration: underline;">Polityce Prywatności</a>.<br><br>
  Jeśli nie chcesz otrzymywać od nas więcej wiadomości, po prostu odpowiedz na tego \
maila słowem &#8222;Wypisz&#8221;.
</div>"""


# ---------------------------------------------------------------------------
# PUBLICZNE API
# ---------------------------------------------------------------------------

def generate_rodo_clause(
    client_name: str,
    privacy_policy_url: str,
) -> str:
    """
    Generuje klauzulę RODO doklejaną pod stopką biznesową klienta.

    Realizuje obowiązek informacyjny z art. 13/14 RODO przy cold-email
    opartym na uzasadnionym interesie (art. 6 ust. 1 lit. f RODO)
    oraz zapewnia prosty mechanizm opt-out (odpowiedź "Wypisz").

    Args:
        client_name:         Nazwa prawna firmy-administratora danych (z KRS).
        privacy_policy_url:  URL do polityki prywatności (Client.privacy_policy_url).

    Returns:
        HTML string z klauzulą. Pusty string przy błędzie.
    """
    try:
        return _RODO_CLAUSE_TEMPLATE.format(
            client_name=client_name or "Firmę",
            privacy_policy_url=privacy_policy_url or "#",
        )
    except Exception as e:
        logger.error(f"[COMPLIANCE] Błąd generowania klauzuli RODO: {e}")
        return ""


import os
from functools import lru_cache
from app.kms_client import decrypt_credential

@lru_cache(maxsize=1)
def _get_rodo_salt() -> str:
    """Odszyfrowuje (by KMS) i buforuje sól kryptograficzną do hashowania zapisaną w .env."""
    encrypted_salt = os.getenv("RODO_SALT_ENCRYPTED")
    if not encrypted_salt:
        logger.warning("[COMPLIANCE] RODO_SALT_ENCRYPTED brak w env! Hashe będą słabsze.")
        return ""
    try:
        return decrypt_credential(encrypted_salt)
    except Exception as e:
        logger.error(f"[COMPLIANCE] KMS Błąd deszyfrowania soli RODO: {e}")
        return ""

def get_value_hash(value: str) -> str:
    """
    Generuje kryptograficzny hash SHA-256 dla dowolnej wartości (email lub domena).
    Wzbogacony o sól (z KMS), chroni przed the rainbow_tables attack.
    Deterministyczny — ta sama wartość zawsze daje ten sam hash.
    """
    salt = _get_rodo_salt()
    data_to_hash = value.lower().strip() + salt
    return hashlib.sha256(data_to_hash.encode("utf-8")).hexdigest()


def anonymize_lead(session: Session, lead_id: int) -> bool:
    """
    Realizuje 'Prawo do zapomnienia' (art. 17 RODO) w izolowanym środowisku SaaS.

    Operacje:
    1. Hash e-maila → GlobalOptOut (EMAIL).
    2. Hash domeny → GlobalOptOut (DOMAIN) — blokuje też scouting/research tej firmy.
    3. Bezpowrotne usunięcie danych osobowych z rekordu Lead.
    4. Status 'BLACKLISTED' — lead nie wraca do pipeline'u.

    Args:
        session: Aktywna sesja SQLAlchemy.
        lead_id: ID leada do anonimizacji.

    Returns:
        True jeśli sukces, False przy błędzie.
    """
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        logger.error(f"[COMPLIANCE] anonymize_lead: Lead ID {lead_id} nie istnieje.")
        return False

    try:
        original_email = lead.target_email or ""
        domain = original_email.split("@")[-1] if "@" in original_email else ""

        # 1. Blacklist e-maila
        if original_email:
            _add_to_blacklist(session, original_email, "EMAIL")
            lead.target_email = "[ZANONIMIZOWANO_RODO]"

        # 2. Blacklist domeny (blokuje scouting i research tej firmy)
        if domain:
            _add_to_blacklist(session, domain, "DOMAIN")

        # 3. Usuwanie danych osobowych
        lead.generated_email_subject = None
        lead.generated_email_body = None
        lead.reply_content = None
        lead.reply_analysis = None
        lead.ai_analysis_summary = (
            f"[USUNIĘTO ZGODNIE Z ART 17 RODO – {datetime.now(PL_TZ).strftime('%Y-%m-%d')}]"
        )

        # 4. Trwała blokada
        lead.status = "BLACKLISTED"
        lead.last_action_at = datetime.now(PL_TZ)

        session.commit()
        logger.info(
            f"[COMPLIANCE] Lead {lead_id} zanonimizowany. "
            f"EMAIL + DOMENA '{domain}' dodane do czarnej listy."
        )
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"[COMPLIANCE] Błąd anonimizacji leada {lead_id}: {e}", exc_info=True)
        return False


def is_opted_out(session: Session, email: str) -> bool:
    """
    Bramka wysyłkowa — sprawdza hash e-maila.

    Args:
        session: Sesja SQLAlchemy.
        email:   Adres e-mail odbiorcy.

    Returns:
        True jeśli na czarnej liście (NIE wysyłaj), False jeśli OK.
    """
    if not email or not email.strip():
        return True

    email_hash = get_value_hash(email)
    if session.query(OptOut).filter(
        OptOut.value_hash == email_hash,
        OptOut.entry_type == "EMAIL",
    ).first():
        logger.warning("[COMPLIANCE] Blokada wysyłki: e-mail na czarnej liście (EMAIL).")
        return True

    return False


def is_domain_opted_out(session: Session, domain: str) -> bool:
    """
    Bramka scoutingu/researchu — sprawdza hash domeny.

    Wywoływana:
    - scout.py: przed dodaniem firmy do bazy (oszczędzamy lead slot)
    - researcher.py: przed Crawl4AI (oszczędzamy zasoby serwera)

    Args:
        session: Sesja SQLAlchemy.
        domain:  Czysta domena firmy (np. 'firma.pl').

    Returns:
        True jeśli na czarnej liście (POMIŃ firmę), False jeśli OK.
    """
    if not domain or not domain.strip():
        return False  # Brak domeny = nie blokuj (nie wiadomo kto to)

    domain_hash = get_value_hash(domain)
    if session.query(OptOut).filter(
        OptOut.value_hash == domain_hash,
        OptOut.entry_type == "DOMAIN",
    ).first():
        logger.warning(f"[COMPLIANCE] Blokada domeny '{domain}' (DOMAIN blacklist).")
        return True

    return False


def add_domain_to_blacklist(session: Session, domain: str) -> None:
    """
    Publiczna funkcja do ręcznego dodania domeny do czarnej listy.
    Używana np. przez inbox agent przy wykryciu odpowiedzi 'Wypisz'.
    """
    if domain:
        _add_to_blacklist(session, domain, "DOMAIN")
        session.commit()


# ---------------------------------------------------------------------------
# PRYWATNE HELPERY
# ---------------------------------------------------------------------------

def _add_to_blacklist(
    session: Session,
    value: str,
    entry_type: EntryType,
) -> None:
    """
    Zapisuje wyłącznie bezpieczny hash do czarnej listy (idempotentne).
    Nie robi commit — caller odpowiada za transakcję.
    """
    value_hash = get_value_hash(value)
    if not session.query(OptOut).filter(OptOut.value_hash == value_hash).first():
        session.add(OptOut(
            value_hash=value_hash,
            entry_type=entry_type,
            added_at=datetime.now(PL_TZ),
        ))
        logger.info(f"[COMPLIANCE] Dodano do blacklisty: type={entry_type}, hash={value_hash[:12]}...")

# KOREKTA ARCHITEKTURY: RODO MANAGER (SAAS TENANT ISOLATION)

Architektura systemu uległa doprecyzowaniu. Stopka biznesowa HTML (dane firmy, KRS, NIP) jest przechowywana i zarządzana w bazie danych. Moduł `rodo_manager.py` odpowiada WYŁĄCZNIE za doklejenie obowiązkowej klauzuli RODO (art. 14), linku do wypisu (PKE) oraz zarządzanie globalną, zaszyfrowaną czarną listą (Tenant Isolation).

Twoim zadaniem jest całkowite nadpisanie pliku `app/rodo_manager.py` poniższym, bezpiecznym kodem:

```python
# app/rodo_manager.py
"""
NEXUS COMPLIANCE ENGINE - Moduł Zgodności z GDPR (RODO) i PKE
Zaprojektowany dla modelu SaaS (Data Processor / Tenant Isolation).
UWAGA: Stopka biznesowa (KSH) jest pobierana z bazy danych. Ten moduł obsługuje tylko RODO.
"""

import hashlib
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import Lead, OptOut # Model OptOut musi posiadać pole 'email_hash' (String 64)

logger = logging.getLogger("nexus_compliance")

# ---------------------------------------------------------------------------
# SZABLON RODO & OPT-OUT (DOKLEJANY NA SAMYM DOLE MAILA)
# ---------------------------------------------------------------------------

_RODO_CLAUSE_TEMPLATE = """\
<div style="margin-top: 15px; font-family: Arial, sans-serif; font-size: 10px; color: #888888; line-height: 1.3; border-top: 1px solid #eeeeee; padding-top: 10px;">
  Administratorem Twoich danych osobowych jest {client_name}. Twój adres e-mail został pozyskany z publicznie dostępnych źródeł. Kontaktujemy się z Tobą na podstawie naszego prawnie uzasadnionego interesu (art. 6 ust. 1 lit. f RODO), w celu zaproszenia do nawiązania relacji B2B. Pełne informacje o tym, jak przetwarzamy Twoje dane, znajdziesz w naszej <a href="{privacy_policy_url}" style="color: #888888; text-decoration: underline;">Polityce Prywatności</a>.<br><br>
  Jeśli nie chcesz otrzymywać od nas więcej wiadomości, odpowiedz "Wypisz" lub kliknij <a href="{opt_out_link}" style="color: #888888; text-decoration: underline;">tutaj, aby zrezygnować</a>.
</div>
"""

# ---------------------------------------------------------------------------
# PUBLICZNE API
# ---------------------------------------------------------------------------

def generate_rodo_clause(client_name: str, privacy_policy_url: str, opt_out_link: str) -> str:
    """
    Generuje klauzulę RODO doklejaną pod stopką biznesową klienta.
    """
    try:
        return _RODO_CLAUSE_TEMPLATE.format(
            client_name=client_name or "Firmę",
            privacy_policy_url=privacy_policy_url or "#",
            opt_out_link=opt_out_link or "#"
        )
    except Exception as e:
        logger.error(f"[COMPLIANCE] Błąd generowania klauzuli RODO: {e}")
        return ""

def get_email_hash(email: str) -> str:
    """Generuje kryptograficzny hash SHA-256 dla adresu e-mail."""
    return hashlib.sha256(email.lower().strip().encode('utf-8')).hexdigest()

def anonymize_lead(session: Session, lead_id: int) -> bool:
    """
    Realizuje 'Prawo do zapomnienia' (art. 17 RODO) w izolowanym środowisku SaaS.
    
    1. Generuje hash e-maila i dodaje do GlobalOptOut.
    2. Bezpowrotnie usuwa dane osobowe z rekordu Lead.
    """
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False

    try:
        original_email = lead.target_email or ""
        
        # 1. Kryptograficzna czarna lista
        if original_email:
            email_hash = get_email_hash(original_email)
            _add_hash_to_opt_out(session, email_hash)
            lead.target_email = f"[ZANONIMIZOWANO_RODO]"
        
        # 2. Usuwanie danych
        lead.generated_email_subject = None
        lead.generated_email_body = None
        lead.reply_content = None
        lead.reply_analysis = None
        lead.ai_analysis_summary = f"[USUNIĘTO ZGODNIE Z ART 17 RODO – {datetime.now().strftime('%Y-%m-%d')}]"

        # 3. Zmiana statusu
        lead.status = "BLACKLISTED"
        lead.last_action_at = datetime.now()

        session.commit()
        logger.info(f"[COMPLIANCE] Lead {lead_id} zanonimizowany. Hash dodany do czarnej listy.")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"[COMPLIANCE] Błąd anonimizacji leada {lead_id}: {e}", exc_info=True)
        return False

def is_opted_out(session: Session, email: str) -> bool:
    """
    Bramka wysyłkowa. Sprawdza, czy kryptograficzny hash e-maila jest na czarnej liście.
    """
    if not email or not email.strip():
        return True

    email_hash = get_email_hash(email)

    if session.query(OptOut).filter(OptOut.email_hash == email_hash).first():
        logger.warning(f"[COMPLIANCE] Blokada wysyłki: E-mail jest na kryptograficznej czarnej liście.")
        return True

    return False

# ---------------------------------------------------------------------------
# PRYWATNE HELPERY
# ---------------------------------------------------------------------------

def _add_hash_to_opt_out(session: Session, email_hash: str) -> None:
    """Zapisuje wyłącznie bezpieczny hash."""
    existing = session.query(OptOut).filter(OptOut.email_hash == email_hash).first()
    if not existing:
        new_optout = OptOut(email_hash=email_hash, added_at=datetime.now())
        session.add(new_optout)
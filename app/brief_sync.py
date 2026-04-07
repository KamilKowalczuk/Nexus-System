# app/brief_sync.py
"""
NEXUS BRIEF SYNC v2 — Inteligentna synchronizacja Brief (PayloadCMS) → Client (Nexus)

Zamiast REST API, czyta BEZPOŚREDNIO z tabel Payload w wspólnej bazie PostgreSQL.

Funkcjonalności:
    - Wykrywanie zmian (brief_updated_at vs ostatni sync)
    - Dezaktywacja klientów których brief został usunięty/anulowany
    - Logowanie CO DOKŁADNIE się zmieniło
    - Częsty polling (co 30 min w main.py, na żądanie w dashboard)

Tabele Payload (snake_case, ta sama baza Railway):
    orders  — zamówienia (subscription_status, daily_limit, brief_id)
    briefs  — konfiguracje klientów (company_name, imap_password itd.)
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import Client, Campaign

logger = logging.getLogger("nexus_brief_sync")

# Mapowanie tone_of_voice (Payload select value → Nexus string)
_TONE_MAP = {
    "formal": "Formalny / Korporacyjny",
    "professional": "Profesjonalny / Partnerski",
    "direct": "Bezpośredni / Konkretny",
    "technical": "Techniczny / Ekspercki",
}

# Mapowanie action_mode (Payload) → sending_mode (Nexus)
_ACTION_MODE_MAP = {
    "auto_send": "AUTO",
    "save_to_drafts": "DRAFT",
}

# Pola które NIE powinny być nadpisywane wartością None (zachowaj istniejące)
_SKIP_IF_NONE = {
    "smtp_user", "smtp_password", "smtp_server", "smtp_port",
    "imap_server", "imap_port", "html_footer",
}

# Pola zarządzane WYŁĄCZNIE przez Nexus (dashboard / API gov.pl / admin).
# Brief sync NIGDY ich nie rusza — nawet jeśli brief zwraca jakąś wartość.
_NEXUS_MANAGED_FIELDS = {
    "scout_model", "researcher_model", "writer_model",  # LLM config per-agent
    "html_footer",          # Stopka generowana przez API gov.pl — nie nadpisuj briefem
    "privacy_policy_url",   # RODO compliance
    "opt_out_link",         # RODO compliance
    "nip", "legal_name",    # Dane z KRS/REGON
    "attachment_filename",  # Załącznik ustawiony ręcznie
}


def _fetch_active_briefs(session: Session) -> list[dict]:
    """
    Pobiera aktywne zamówienia z wypełnionym briefem bezpośrednio z tabel Payload.
    Używa JOIN orders → briefs przez klucz obcy brief_id.
    """
    sql = text("""
        SELECT
            o.id             AS order_id,
            o.daily_limit,
            o.customer_email,
            o.subscription_status,
            b.id             AS brief_id,
            b.company_name,
            b.industry,
            b.sender_name,
            b.website_url,
            b.action_mode,
            b.campaign_goal,
            b.value_proposition,
            b.ideal_customer_profile,
            b.tone_of_voice,
            b.negative_constraints,
            b.case_studies,
            b.signature_html,
            b.warmup_strategy,
            b.auth_method,
            b.imap_host,
            b.imap_port,
            b.imap_user,
            b.imap_password,
            b.oauth_provider,
            b.oauth_email,
            b.oauth_refresh_token,
            b.updated_at     AS brief_updated_at
        FROM orders o
        JOIN briefs b ON b.id = o.brief_id
        WHERE o.subscription_status = 'active'
          AND o.brief_id IS NOT NULL
        ORDER BY o.id
    """)

    rows = session.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def _map_row_to_client_fields(row: dict) -> dict:
    """
    Mapuje wiersz z JOIN orders+briefs na pola modelu Client (Nexus).
    Szyfrogram IMAP/OAuth przekazywany bez zmian — KMS odszyfrowuje przy wysyłce.
    """
    auth_method = row.get("auth_method", "nexus_lookalike_domain")

    smtp_user = None
    smtp_password = None
    smtp_server = None
    smtp_port = 465
    imap_server = None
    imap_port = 993

    if auth_method == "imap_encrypted_vault":
        smtp_user = row.get("imap_user")
        smtp_password = row.get("imap_password")  # AS-IS: "ENCRYPTED:..."
        smtp_server = row.get("imap_host")
        imap_server = row.get("imap_host")
        try:
            p = int(row.get("imap_port") or 993)
            imap_port = p
            smtp_port = p
        except (TypeError, ValueError):
            pass

    elif auth_method == "oauth":
        smtp_user = row.get("oauth_email")
        smtp_password = row.get("oauth_refresh_token")  # AS-IS: "ENCRYPTED:..."
        provider = row.get("oauth_provider") or "google"
        if provider == "google":
            smtp_server = "smtp.gmail.com"
            imap_server = "imap.gmail.com"
            smtp_port = 587
        elif provider == "microsoft":
            smtp_server = "smtp.office365.com"
            imap_server = "outlook.office365.com"
            smtp_port = 587

    # nexus_lookalike_domain: dane uzupełniane ręcznie przez admina

    tone_raw = row.get("tone_of_voice") or ""
    tone = _TONE_MAP.get(tone_raw, tone_raw)

    return {
        "name": (row.get("company_name") or "").strip(),
        "industry": row.get("industry"),
        "value_proposition": row.get("value_proposition"),
        "ideal_customer_profile": row.get("ideal_customer_profile"),
        "tone_of_voice": tone or None,
        "negative_constraints": row.get("negative_constraints"),
        "case_studies": row.get("case_studies"),
        "sender_name": row.get("sender_name"),
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "imap_server": imap_server,
        "imap_port": imap_port,
        "html_footer": row.get("signature_html") or None,
        "sending_mode": _ACTION_MODE_MAP.get(row.get("action_mode") or "", "DRAFT"),
        "warmup_enabled": bool(row.get("warmup_strategy", True)),
        "warmup_start_limit": 2,
        "warmup_increment": 2,
        "daily_limit": int(row.get("daily_limit") or 50),
        "status": "ACTIVE",
        # Payload CMS relation (twarde FK)
        "payload_order_id": row.get("order_id"),
        "payload_brief_id": row.get("brief_id"),
    }


def _detect_changes(client: Client, new_fields: dict) -> list[str]:
    """
    Porównuje obecne dane klienta z nowymi z briefu.
    Zwraca listę opisów zmian (pusta = brak zmian).
    """
    changes = []
    for key, new_val in new_fields.items():
        if key in ("status", "warmup_start_limit", "warmup_increment"):
            continue  # Pola zarządzane przez Nexus, nie brief

        # Pola zarządzane wyłącznie przez Nexus — sync nie rusza
        if key in _NEXUS_MANAGED_FIELDS:
            continue

        old_val = getattr(client, key, None)

        # Nie nadpisuj None dla pól technicznych (smtp_password itp.)
        if new_val is None and key in _SKIP_IF_NONE:
            continue

        # Porównanie z normalizacją typów
        if str(old_val or "") != str(new_val or ""):
            # Maskuj hasła w logach
            if "password" in key or "token" in key:
                changes.append(f"  • {key}: [zmienione]")
            else:
                old_short = str(old_val or "")[:50]
                new_short = str(new_val or "")[:50]
                changes.append(f"  • {key}: '{old_short}' → '{new_short}'")

    return changes


def _upsert_client(session: Session, fields: dict) -> tuple[Client, bool, list[str]]:
    """
    Tworzy lub aktualizuje Client. Klucz unikalności: name.
    Zwraca (client, created: bool, changes: list[str]).
    """
    name = fields.get("name")
    if not name:
        raise ValueError("[SYNC] Brief nie ma company_name — pomijam.")

    client = session.query(Client).filter(Client.name == name).first()
    created = False
    changes = []

    if not client:
        # Przy tworzeniu nie ustawiaj pól zarządzanych przez Nexus
        # (zostaną z domyślnymi wartościami z modelu ORM)
        create_fields = {k: v for k, v in fields.items() if k not in _NEXUS_MANAGED_FIELDS}
        client = Client(**create_fields)
        session.add(client)
        session.flush()
        created = True
        logger.info(f"[SYNC] ✅ Nowy klient: '{name}'")
    else:
        # Wykryj CO się zmieniło
        changes = _detect_changes(client, fields)

        if changes:
            # Aktualizuj pola konfiguracyjne (tylko te z briefu, nie Nexus-managed)
            for key, value in fields.items():
                if key in _NEXUS_MANAGED_FIELDS:
                    continue  # Nigdy nie nadpisuj pól zarządzanych przez Nexus
                if value is None and key in _SKIP_IF_NONE:
                    continue
                if value is not None:
                    setattr(client, key, value)
            logger.info(f"[SYNC] 🔄 Zaktualizowano '{name}':\n" + "\n".join(changes))
        else:
            logger.debug(f"[SYNC] ✔️ '{name}' — bez zmian")

    return client, created, changes


def _ensure_campaign(session: Session, client: Client, row: dict) -> None:
    """Tworzy domyślną kampanię jeśli klient nie ma żadnej aktywnej."""
    existing = session.query(Campaign).filter(
        Campaign.client_id == client.id,
        Campaign.status == "ACTIVE",
    ).first()
    if existing:
        return

    goal = row.get("campaign_goal") or ""
    icp = row.get("ideal_customer_profile") or ""
    strategy_prompt = f"{goal}\n\nICP: {icp}".strip()

    campaign = Campaign(
        client_id=client.id,
        name=f"Kampania {client.name}",
        status="ACTIVE",
        strategy_prompt=strategy_prompt,
        target_region="PL",
    )
    session.add(campaign)
    logger.info(f"[SYNC] 📋 Utworzono kampanię dla '{client.name}'")


def _deactivate_removed_clients(session: Session, active_names: set[str]) -> int:
    """
    Dezaktywuje klientów których brief został usunięty lub zamówienie anulowane.
    Nie kasuje danych — tylko status PAUSED.
    """
    # Klienci zsynchronizowani z Payload (mają payload_brief_id)
    synced_clients = session.query(Client).filter(
        Client.payload_brief_id.isnot(None),
        Client.status == "ACTIVE",
    ).all()

    deactivated = 0
    for client in synced_clients:
        if client.name not in active_names:
            client.status = "PAUSED"
            logger.warning(
                f"[SYNC] ⏸️ Dezaktywowano '{client.name}' — "
                f"brief/zamówienie usunięte lub anulowane w Payload"
            )
            deactivated += 1

    return deactivated


def sync_briefs_to_clients(session: Session) -> dict:
    """
    Główna funkcja synchronizacji v2. Wywołuj przy starcie, co 30 min, i z dashboardu.

    Czyta bezpośrednio z tabel Payload (briefs JOIN orders) — bez REST API.

    Returns:
        dict z kluczami: created, updated, unchanged, deactivated, errors
    """
    result = {"created": 0, "updated": 0, "unchanged": 0, "deactivated": 0, "errors": 0}

    logger.info("[SYNC] Startuję synchronizację Brief → Client (direct DB)...")

    try:
        rows = _fetch_active_briefs(session)
    except Exception as e:
        logger.error(f"[SYNC] Błąd odczytu tabel Payload: {e}")
        session.rollback()  # CRITICAL: reset stanu transakcji — bez tego connection pool zwraca "aborted" connection do kolejnych sesji
        return result

    if not rows:
        logger.info("[SYNC] Brak aktywnych zamówień z briefami.")
        # Dezaktywuj WSZYSTKICH zsynchronizowanych klientów
        deactivated = _deactivate_removed_clients(session, set())
        if deactivated > 0:
            result["deactivated"] = deactivated
            session.commit()
        return result

    active_names = set()

    for row in rows:
        try:
            fields = _map_row_to_client_fields(row)
            name = fields.get("name")
            if name:
                active_names.add(name)

            client, created, changes = _upsert_client(session, fields)
            _ensure_campaign(session, client, row)
            session.commit()

            if created:
                result["created"] += 1
            elif changes:
                result["updated"] += 1
            else:
                result["unchanged"] += 1

        except ValueError as e:
            logger.warning(str(e))
            result["errors"] += 1
        except Exception as e:
            session.rollback()
            logger.error(
                f"[SYNC] Błąd synchronizacji '{row.get('company_name')}': {e}"
            )
            result["errors"] += 1

    # Dezaktywuj klientów których brief zniknął z Payload
    deactivated = _deactivate_removed_clients(session, active_names)
    if deactivated > 0:
        result["deactivated"] = deactivated
        session.commit()

    total = result["created"] + result["updated"] + result["unchanged"]
    logger.info(
        f"[SYNC] Zakończono. "
        f"Nowych: {result['created']}, "
        f"Zaktualizowanych: {result['updated']}, "
        f"Bez zmian: {result['unchanged']}, "
        f"Dezaktywowanych: {result['deactivated']}, "
        f"Błędów: {result['errors']}"
    )
    return result

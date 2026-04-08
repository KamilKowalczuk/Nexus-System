# app/alerts.py
"""
NEXUS OPERATOR ALERTS — powiadomienia email dla operatora systemu.

Wysyła email do operatora gdy krytyczny serwis (DeBounce, etc.) pada.
Throttling via Redis — max 1 alert tego samego typu co 4 godziny.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger("nexus_alerts")

PL_TZ = ZoneInfo("Europe/Warsaw")

# Konfiguracja SMTP operatora — z env vars
_SMTP_SERVER = "smtp.purelymail.com"
_SMTP_PORT = 465
_EMAIL_USER = os.getenv("EMAIL_USER", "")
_EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# Email docelowy dla alertów (domyślnie ten sam co nadawca)
_ALERT_RECIPIENT = os.getenv("OPERATOR_ALERT_EMAIL") or _EMAIL_USER

# Cooldown — nie bombarduj tymi samymi alertami
_ALERT_COOLDOWN_SECONDS = 4 * 3600  # 4 godziny


def _get_cooldown_key(alert_type: str) -> str:
    return f"alert:cooldown:{alert_type}"


def _is_on_cooldown(alert_type: str) -> bool:
    """Sprawdza czy alert był już wysłany w oknie cooldown (Redis)."""
    try:
        from app.cache_manager import cache_manager
        val = cache_manager.redis.get(_get_cooldown_key(alert_type))
        return val is not None
    except Exception:
        return False  # Redis niedostępny — pozwól wysłać


def _set_cooldown(alert_type: str) -> None:
    """Ustawia cooldown w Redis (TTL = 4h)."""
    try:
        from app.cache_manager import cache_manager
        cache_manager.redis.set(
            _get_cooldown_key(alert_type),
            datetime.now(PL_TZ).isoformat(),
            ttl=_ALERT_COOLDOWN_SECONDS,
        )
    except Exception:
        pass  # Redis niedostępny — nie blokuj działania


def send_operator_alert(alert_type: str, subject: str, body: str) -> bool:
    """
    Wysyła email do operatora z alertem o krytycznym błędzie.

    Args:
        alert_type: Unikalny identyfikator alertu (np. "debounce_down") — używany do cooldown
        subject:    Temat emaila
        body:       Treść emaila (plain text)

    Returns:
        True jeśli wysłano (lub był na cooldown), False jeśli błąd wysyłki
    """
    if not _EMAIL_USER or not _EMAIL_PASSWORD:
        logger.warning("[ALERT] Brak konfiguracji SMTP (EMAIL_USER/EMAIL_PASSWORD) — alert pominięty")
        return False

    if not _ALERT_RECIPIENT:
        logger.warning("[ALERT] Brak OPERATOR_ALERT_EMAIL — alert pominięty")
        return False

    # Cooldown check — żeby nie zalać skrzynki
    if _is_on_cooldown(alert_type):
        logger.debug(f"[ALERT] '{alert_type}' na cooldown — pomijam (max 1 alert/4h)")
        return True  # Traktujemy jako "handled"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 NEXUS ALERT: {subject}"
        msg["From"] = f"NEXUS Engine <{_EMAIL_USER}>"
        msg["To"] = _ALERT_RECIPIENT

        now_str = datetime.now(PL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        full_body = (
            f"NEXUS Engine — Alert Operatorski\n"
            f"Czas: {now_str}\n"
            f"Typ: {alert_type}\n"
            f"{'─' * 50}\n\n"
            f"{body}\n\n"
            f"{'─' * 50}\n"
            f"Ten alert nie będzie powtórzony przez 4 godziny.\n"
            f"Jeśli problem nadal trwa po tym czasie, dostaniesz kolejne powiadomienie."
        )

        msg.attach(MIMEText(full_body, "plain", "utf-8"))

        with smtplib.SMTP_SSL(_SMTP_SERVER, _SMTP_PORT) as server:
            server.login(_EMAIL_USER, _EMAIL_PASSWORD)
            server.sendmail(_EMAIL_USER, _ALERT_RECIPIENT, msg.as_string())

        _set_cooldown(alert_type)
        logger.info(f"[ALERT] ✅ Wysłano alert '{alert_type}' → {_ALERT_RECIPIENT}")
        return True

    except Exception as e:
        logger.error(f"[ALERT] ❌ Błąd wysyłki alertu '{alert_type}': {e}")
        return False

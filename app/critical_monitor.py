# app/critical_monitor.py
"""
NEXUS CRITICAL API MONITOR — nadzór nad kluczowymi serwisami zewnętrznymi.

Śledzi awarie DeBounce, Crawl4AI, Apify.
Gdy awaria jest krytyczna (billing 402, zbyt wiele timeoutów) → zapisuje flag file
i wysyła alert email. Silnik main.py czyta flag file na początku każdej iteracji
i zatrzymuje się jeśli flaga jest ustawiona.

Operator loguje się → usuwa flagę → restartuje silnik z GUI.

FLAG FILE: .critical_stop (JSON: {reason, api, timestamp, consecutive})
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("critical_monitor")
PL_TZ = ZoneInfo("Europe/Warsaw")

# Ścieżka do flag file (obok main.py)
_FLAG_FILE = Path(__file__).parent.parent / ".critical_stop"

# Progi kolejnych błędów przed uznaniem za krytyczne
_THRESHOLDS = {
    "debounce":  5,   # 5 kolejnych API_DOWN → stop
    "crawl4ai":  5,   # 5 kolejnych błędów headless browser → stop
    "apify":     8,   # 8 kolejnych błędów → stop (Apify jest mniej krytyczny)
}

# Thread-safe liczniki awarii
_lock = threading.Lock()
_consecutive_failures: dict[str, int] = {
    "debounce":  0,
    "crawl4ai":  0,
    "apify":     0,
}


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def record_failure(api_name: str) -> bool:
    """
    Rejestruje kolejną awarię API. Jeśli próg przekroczony → triggeruje stop.

    Returns:
        True jeśli po tym wywołaniu nastąpił critical stop, False w przeciwnym razie
    """
    with _lock:
        _consecutive_failures[api_name] = _consecutive_failures.get(api_name, 0) + 1
        count = _consecutive_failures[api_name]

    threshold = _THRESHOLDS.get(api_name, 5)
    logger.debug(f"[MONITOR] {api_name} failure #{count}/{threshold}")

    if count >= threshold:
        reason = (
            f"{api_name.upper()} API nie odpowiada od {count} kolejnych prób. "
            f"Prawdopodobna awaria serwisu lub wyczerpanie kredytów."
        )
        trigger_stop(api_name=api_name, reason=reason, consecutive=count)
        return True

    return False


def record_success(api_name: str) -> None:
    """Rejestruje sukces — resetuje licznik awarii dla danego API."""
    with _lock:
        prev = _consecutive_failures.get(api_name, 0)
        _consecutive_failures[api_name] = 0
    if prev > 0:
        logger.debug(f"[MONITOR] {api_name} wróciło do normy (reset po {prev} błędach)")


def trigger_stop(api_name: str, reason: str, consecutive: int = 1) -> None:
    """
    Zapisuje flag file i wysyła alert email.
    Wywołuj przy krytycznej awarii (np. HTTP 402 — brak kredytów).

    Jeśli flag file już istnieje → nie nadpisuj (nie podwajaj alertów).
    """
    if _FLAG_FILE.exists():
        logger.debug("[MONITOR] Flag file już istnieje — pomijam trigger")
        return

    now = datetime.now(PL_TZ)
    payload = {
        "api": api_name,
        "reason": reason,
        "consecutive": consecutive,
        "stopped_at": now.isoformat(),
    }

    try:
        _FLAG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        logger.critical(
            f"[MONITOR] 🚨 CRITICAL STOP — {api_name.upper()}: {reason} "
            f"(plik: {_FLAG_FILE})"
        )
    except Exception as e:
        logger.error(f"[MONITOR] Nie udało się zapisać flag file: {e}")
        return

    # Wyślij alert email
    _send_stop_alert(api_name=api_name, reason=reason, consecutive=consecutive, stopped_at=now)


def is_stopped() -> tuple[bool, str]:
    """
    Sprawdza czy silnik powinien się zatrzymać.

    Returns:
        (True, reason_str) jeśli flag file istnieje
        (False, "") w przeciwnym razie
    """
    if not _FLAG_FILE.exists():
        return False, ""

    try:
        data = json.loads(_FLAG_FILE.read_text())
        api = data.get("api", "?").upper()
        reason = data.get("reason", "Nieznany powód")
        stopped_at = data.get("stopped_at", "?")
        return True, f"[{api}] {reason} (od: {stopped_at})"
    except Exception:
        return True, "Krytyczna awaria (flag file uszkodzony)"


def clear_stop() -> bool:
    """
    Usuwa flag file — używane przez dashboard przy restarcie silnika.

    Returns:
        True jeśli plik istniał i został usunięty
    """
    if _FLAG_FILE.exists():
        _FLAG_FILE.unlink()
        with _lock:
            for key in _consecutive_failures:
                _consecutive_failures[key] = 0
        logger.info("[MONITOR] Flag file usunięty — silnik może się uruchomić")
        return True
    return False


def get_status() -> dict:
    """Zwraca pełny status monitora — dla dashboardu."""
    stopped, reason = is_stopped()
    with _lock:
        failures = dict(_consecutive_failures)
    return {
        "stopped": stopped,
        "reason": reason if stopped else None,
        "consecutive_failures": failures,
        "flag_file": str(_FLAG_FILE),
    }


# ---------------------------------------------------------------------------
# PRIVATE
# ---------------------------------------------------------------------------

_ALERT_MESSAGES = {
    "debounce": (
        "DeBounce API nie odpowiada (zbyt wiele kolejnych błędów).\n\n"
        "Możliwe przyczyny:\n"
        "  - Wyczerpane kredyty → zaloguj się na debounce.io i doładuj\n"
        "  - Chwilowa awaria serwisu → sprawdź status.debounce.io\n\n"
        "Silnik NEXUS zatrzymał się. Żadne emaile nie zostały wysłane bez weryfikacji.\n\n"
        "Jak wznowić:\n"
        "  1. Rozwiąż problem z DeBounce\n"
        "  2. Zaloguj się do panelu NEXUS\n"
        "  3. Kliknij 'URUCHOM' — silnik sam się wyczyści i ruszy"
    ),
    "crawl4ai": (
        "Crawl4AI (lokalny headless browser) nie działa.\n\n"
        "Możliwe przyczyny:\n"
        "  - Brak pamięci RAM na serwerze → sprawdź 'docker stats'\n"
        "  - Playwright/Chromium crash → zrestartuj kontener\n"
        "  - Timeout na zbyt dużych stronach\n\n"
        "Silnik NEXUS zatrzymał się. Scraping stron firmowych jest wstrzymany.\n\n"
        "Jak wznowić:\n"
        "  1. Sprawdź logi kontenera\n"
        "  2. Zaloguj się do panelu NEXUS\n"
        "  3. Kliknij 'URUCHOM'"
    ),
    "apify": (
        "Apify API nie odpowiada (zbyt wiele kolejnych błędów przy scoutingu).\n\n"
        "Możliwe przyczyny:\n"
        "  - Wyczerpane środki → zaloguj się na apify.com i doładuj\n"
        "  - Nieprawidłowy klucz API → sprawdź APIFY_API_KEY w .env\n"
        "  - Chwilowa awaria serwisu\n\n"
        "Silnik NEXUS zatrzymał się. Scouting nowych firm jest wstrzymany.\n\n"
        "Jak wznowić:\n"
        "  1. Rozwiąż problem z Apify\n"
        "  2. Zaloguj się do panelu NEXUS\n"
        "  3. Kliknij 'URUCHOM'"
    ),
}


def _send_stop_alert(api_name: str, reason: str, consecutive: int, stopped_at: datetime) -> None:
    try:
        from app.alerts import send_operator_alert
        msg = _ALERT_MESSAGES.get(api_name, f"Krytyczna awaria: {reason}")
        full_body = (
            f"Liczba kolejnych błędów: {consecutive}\n"
            f"Czas zatrzymania: {stopped_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{msg}"
        )
        send_operator_alert(
            alert_type=f"critical_stop_{api_name}",
            subject=f"Silnik ZATRZYMANY — {api_name.upper()} nie działa",
            body=full_body,
        )
    except Exception as e:
        logger.error(f"[MONITOR] Błąd wysyłki alertu: {e}")

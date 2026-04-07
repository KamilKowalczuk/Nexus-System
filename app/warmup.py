# app/warmup.py
"""
WARMUP CALCULATOR - Email Sending Ramp-Up
Logic: today's limit = last_active_day_sends + increment

Zamiast liczyć dni od startu (co się psuje gdy silnik był wyłączony),
szukamy OSTATNIEGO DNIA w którym faktycznie wysłano maile i dodajemy increment.

Przykład (increment=2, target=50):
  Dzień 1 (brak historii)        → start_limit = 2
  Dzień 2 (ostatni dzień: 2)     → 2 + 2 = 4
  Dzień 3 (ostatni dzień: 4)     → 4 + 2 = 6
  --- silnik wyłączony 3 dni ---
  Dzień 7 (ostatni dzień: 6)     → 6 + 2 = 8  (nie resetuje!)
  --- warmup dobiegł końca ---
  Dzień N (ostatni dzień: 50)    → pełny limit = 50 (warmup done)
"""

from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
import logging
from sqlalchemy import desc
from app.database import Client, CampaignStatistics, SessionLocal
from app.cache_manager import cache_manager

logger = logging.getLogger("warmup")


def _get_last_active_day(client_id: int) -> tuple[int, date | None]:
    """
    Znajduje ostatni dzień w którym klient faktycznie wysłał maile.

    Returns:
        (emails_sent, date) — lub (0, None) jeśli brak historii
    """
    try:
        with SessionLocal() as session:
            stat = (
                session.query(CampaignStatistics)
                .filter(
                    CampaignStatistics.client_id == client_id,
                    CampaignStatistics.emails_sent > 0,
                )
                .order_by(desc(CampaignStatistics.date))
                .first()
            )
            if stat:
                return int(stat.emails_sent), stat.date
            return 0, None
    except Exception as e:
        logger.warning(f"[WARMUP] Błąd pobierania historii klienta {client_id}: {e}")
        return 0, None


def calculate_daily_limit(client: Client) -> int:
    """
    Oblicza efektywny limit na DZIŚ.

    Logika:
      1. Warmup wyłączony → pełny daily_limit
      2. Brak historii wysyłek → warmup_start_limit (pierwsza doba)
      3. Ostatni dzień wysyłki osiągnął daily_limit → warmup skończony, pełny limit
      4. Normalny krok: last_day_sends + increment (max: daily_limit)

    Args:
        client: Client object from database

    Returns:
        Effective daily limit (int)
    """
    target_limit = client.daily_limit or 50

    # Warmup wyłączony → pełny limit
    if not client.warmup_enabled or not client.warmup_started_at:
        return target_limit

    # ==========================================
    # REDIS CACHE: limit na dziś (TTL do północy)
    # ==========================================
    today_str = datetime.now(PL_TZ).date().isoformat()
    cache_key = f"warmup:limit:client:{client.id}:date:{today_str}"

    try:
        cached_limit = cache_manager.redis.get(cache_key)
    except Exception:
        cached_limit = None

    if cached_limit:
        try:
            limit = int(cached_limit)
            logger.debug(f"⚡ Warmup cache hit for client {client.id}: {limit}")
            return limit
        except Exception:
            pass

    # ==========================================
    # OBLICZENIE NA PODSTAWIE OSTATNIEJ AKTYWNEJ WYSYŁKI
    # ==========================================
    start = client.warmup_start_limit or 2
    increment = client.warmup_increment or 2

    last_sent, last_date = _get_last_active_day(client.id)

    if last_sent == 0:
        # Brak historii — pierwsza doba warmup
        effective_limit = start
        logger.info(
            f"[WARMUP] Klient {client.id}: brak historii wysyłek → "
            f"start_limit={start}"
        )
    elif last_sent >= target_limit:
        # Warmup zakończony — ostatni dzień osiągnął pełny limit
        effective_limit = target_limit
        logger.info(
            f"[WARMUP] Klient {client.id}: warmup zakończony "
            f"(ostatni dzień={last_sent} >= target={target_limit}) → pełny limit"
        )
    else:
        # Normalny krok warmup
        today_limit = last_sent + increment
        effective_limit = min(today_limit, target_limit)
        logger.info(
            f"[WARMUP] Klient {client.id}: ostatni aktywny dzień ({last_date})={last_sent} → "
            f"dziś {effective_limit} (+{increment})"
        )

    # ==========================================
    # CACHE DO PÓŁNOCY
    # ==========================================
    now = datetime.now(PL_TZ)
    midnight = datetime.combine(now.date(), datetime.min.time()) + timedelta(days=1)
    midnight = midnight.replace(tzinfo=PL_TZ)
    seconds_until_midnight = int((midnight - now).total_seconds())

    try:
        cache_manager.redis.set(cache_key, str(effective_limit), ttl=seconds_until_midnight)
        logger.debug(
            f"💾 Cached warmup limit for client {client.id}: {effective_limit} "
            f"(wygasa o północy)"
        )
    except Exception:
        pass

    return effective_limit


def get_warmup_progress(client: Client) -> dict:
    """
    Zwraca szczegółowy status warmup dla dashboardu/monitoringu.
    """
    if not client.warmup_enabled or not client.warmup_started_at:
        return {
            "enabled": False,
            "last_day_sent": None,
            "last_active_date": None,
            "current_limit": client.daily_limit or 50,
            "target_limit": client.daily_limit or 50,
            "progress_percent": 100,
            "is_complete": True,
        }

    target_limit = client.daily_limit or 50
    current_limit = calculate_daily_limit(client)
    last_sent, last_date = _get_last_active_day(client.id)
    days_since_start = (datetime.now(PL_TZ).date() - client.warmup_started_at.date()).days

    progress_percent = int((current_limit / target_limit) * 100) if target_limit > 0 else 100
    is_complete = current_limit >= target_limit

    return {
        "enabled": True,
        "last_day_sent": last_sent,
        "last_active_date": last_date.isoformat() if last_date else None,
        "current_limit": current_limit,
        "target_limit": target_limit,
        "progress_percent": progress_percent,
        "is_complete": is_complete,
        "days_since_start": max(days_since_start, 0),
        "start_date": client.warmup_started_at.date().isoformat(),
        "increment_per_day": client.warmup_increment or 2,
    }


def reset_warmup_cache(client_id: int) -> int:
    """Czyści cache warmup dla konkretnego klienta (po zmianie ustawień)."""
    pattern = f"warmup:limit:client:{client_id}:*"
    keys = cache_manager.redis.keys(pattern)
    deleted = 0
    for key in keys:
        if cache_manager.redis.delete(key):
            deleted += 1
    logger.info(f"🗑️ Cleared {deleted} warmup cache entries for client {client_id}")
    return deleted


def clear_all_warmup_cache() -> int:
    """Czyści cały cache warmup (funkcja serwisowa)."""
    pattern = "warmup:limit:*"
    keys = cache_manager.redis.keys(pattern)
    deleted = 0
    for key in keys:
        if cache_manager.redis.delete(key):
            deleted += 1
    logger.info(f"🗑️ Cleared {deleted} total warmup cache entries")
    return deleted

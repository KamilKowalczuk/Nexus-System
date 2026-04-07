# app/warmup.py
"""
WARMUP CALCULATOR - Email Sending Ramp-Up
NOW WITH: Redis cache for warmup state (faster, distributed-safe)
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")
import logging
from app.database import Client
from app.cache_manager import cache_manager

logger = logging.getLogger("warmup")

def calculate_daily_limit(client: Client) -> int:
    """
    Oblicza efektywny limit na DZIŚ, uwzględniając rozgrzewkę.
    
    OPTIMIZATION: Uses Redis cache for warmup calculations to avoid DB hits.
    
    Args:
        client: Client object from database
    
    Returns:
        Effective daily limit (int)
    """
    target_limit = client.daily_limit or 50
    
    # Jeśli warm-up wyłączony lub brak daty startu -> pełny limit
    if not client.warmup_enabled or not client.warmup_started_at:
        return target_limit

    # ==========================================
    # REDIS CACHE: Warmup calculation result
    # ==========================================
    # Cache key: warmup:limit:client:{id}:date:{YYYY-MM-DD}
    today_str = datetime.now(PL_TZ).date().isoformat()
    cache_key = f"warmup:limit:client:{client.id}:date:{today_str}"
    
    # Try cache first
    cached_limit = cache_manager.redis.get(cache_key)
    if cached_limit:
        try:
            limit = int(cached_limit)
            logger.debug(f"⚡ Warmup cache hit for client {client.id}: {limit}")
            return limit
        except:
            pass  # Cache corrupted, recalculate

    # ==========================================
    # NO CACHE - CALCULATE
    # ==========================================
    
    # Obliczamy ile dni minęło od startu rozgrzewki
    days_passed = (datetime.now(PL_TZ).date() - client.warmup_started_at.date()).days
    
    if days_passed < 0: 
        days_passed = 0  # Zabezpieczenie

    # Wzór: Start + (Dni * Przyrost)
    start = client.warmup_start_limit or 2
    increment = client.warmup_increment or 2
    
    current_warmup_limit = start + (days_passed * increment)
    
    # Limit nie może przekroczyć docelowego 'daily_limit'
    effective_limit = min(current_warmup_limit, target_limit)
    
    # ==========================================
    # CACHE THE RESULT (TTL: until midnight)
    # ==========================================
    # Calculate seconds until midnight
    now = datetime.now(PL_TZ)
    midnight = datetime.combine(now.date(), datetime.min.time()) + timedelta(days=1)
    seconds_until_midnight = int((midnight - now).total_seconds())
    
    cache_manager.redis.set(cache_key, str(effective_limit), ttl=seconds_until_midnight)
    logger.debug(f"💾 Cached warmup limit for client {client.id}: {effective_limit} (expires at midnight)")
    
    return effective_limit


def get_warmup_progress(client: Client) -> dict:
    """
    Returns warmup progress information.
    
    NEW FUNCTION: Provides detailed warmup status for monitoring/dashboard.
    
    Returns:
        {
            "enabled": True/False,
            "days_passed": 5,
            "current_limit": 12,
            "target_limit": 50,
            "progress_percent": 24,
            "is_complete": False
        }
    """
    if not client.warmup_enabled or not client.warmup_started_at:
        return {
            "enabled": False,
            "days_passed": 0,
            "current_limit": client.daily_limit or 50,
            "target_limit": client.daily_limit or 50,
            "progress_percent": 100,
            "is_complete": True
        }
    
    target_limit = client.daily_limit or 50
    current_limit = calculate_daily_limit(client)
    days_passed = (datetime.now(PL_TZ).date() - client.warmup_started_at.date()).days
    
    if days_passed < 0:
        days_passed = 0
    
    progress_percent = int((current_limit / target_limit) * 100) if target_limit > 0 else 100
    is_complete = current_limit >= target_limit
    
    return {
        "enabled": True,
        "days_passed": days_passed,
        "current_limit": current_limit,
        "target_limit": target_limit,
        "progress_percent": progress_percent,
        "is_complete": is_complete,
        "start_date": client.warmup_started_at.date().isoformat(),
        "increment_per_day": client.warmup_increment or 2
    }


def reset_warmup_cache(client_id: int):
    """
    UTILITY: Clear warmup cache for specific client.
    Use when warmup settings change.
    
    Args:
        client_id: Client ID to clear cache for
    """
    pattern = f"warmup:limit:client:{client_id}:*"
    keys = cache_manager.redis.keys(pattern)
    
    deleted = 0
    for key in keys:
        if cache_manager.redis.delete(key):
            deleted += 1
    
    logger.info(f"🗑️ Cleared {deleted} warmup cache entries for client {client_id}")
    return deleted


def clear_all_warmup_cache():
    """
    UTILITY: Clear all warmup cache (maintenance function).
    """
    pattern = "warmup:limit:*"
    keys = cache_manager.redis.keys(pattern)
    
    deleted = 0
    for key in keys:
        if cache_manager.redis.delete(key):
            deleted += 1
    
    logger.info(f"🗑️ Cleared {deleted} total warmup cache entries")
    return deleted

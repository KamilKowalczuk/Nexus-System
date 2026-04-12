# app/rate_limiter.py
"""
RATE LIMITER - Smart Throttling System
Prevents IP bans, manages API limits, adaptive delays.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict
from app.cache_manager import cache_manager
from app.database import Client

logger = logging.getLogger("rate_limiter")

class RateLimiter:
    """
    Unified rate limiting for:
    - Email sending (SendGrid daily/hourly limits)
    - API calls (DeBounce, Crawl4AI, etc.)
    - Adaptive throttling based on responses
    """
    
    # ==========================================
    # CONFIGURATION
    # ==========================================
    
    # SendGrid limits (industry standard for new domains)
    SENDGRID_DAILY_MAX = 500        # Conservative limit for new domains
    SENDGRID_HOURLY_MAX = 50        # Burst protection
    
    # API limits (per minute to avoid 429s)
    DEBOUNCE_PER_MINUTE = 10
    CRAWL4AI_PER_MINUTE = 5       # Concurrent browser limit (local)
    APIFY_PER_MINUTE = 10
    
    # Adaptive delays (seconds)
    MIN_DELAY_BETWEEN_EMAILS = 60   # 1 minute minimum
    MAX_DELAY_BETWEEN_EMAILS = 300  # 5 minutes maximum
    DEFAULT_DELAY = 120             # 2 minutes default
    
    def __init__(self):
        self.cache = cache_manager
    
    # ==========================================
    # EMAIL SENDING RATE LIMITS
    # ==========================================
    
    def check_email_limit(self, client: Client) -> tuple[bool, str]:
        """
        Check if client can send email now.
        
        Checks:
        1. Daily limit (warmup-aware)
        2. Hourly limit (burst protection)
        3. Global SendGrid limits
        
        Returns:
            (can_send: bool, reason: str)
        """
        from app.warmup import calculate_daily_limit
        
        client_id = client.id
        
        # 1. CHECK DAILY LIMIT (warmup-aware)
        daily_limit = calculate_daily_limit(client)
        daily_sent = self.get_emails_sent_today(client_id)
        
        if daily_sent >= daily_limit:
            return False, f"Daily limit reached ({daily_sent}/{daily_limit})"
        
        # 2. CHECK HOURLY LIMIT
        hourly_sent = self.get_emails_sent_this_hour(client_id)
        # FIX: Ensure hourly limit is at least 1 if daily limit > 0
        if daily_limit <= 4:
            hourly_limit = daily_limit  # Small daily limit = allow all per hour
        else:
            hourly_limit = min(daily_limit // 4, self.SENDGRID_HOURLY_MAX)
        
        if hourly_sent >= hourly_limit:
            return False, f"Hourly limit reached ({hourly_sent}/{hourly_limit})"
        
        # 3. CHECK GLOBAL SENDGRID LIMIT (all clients combined)
        global_daily = self.get_global_emails_sent_today()
        
        if global_daily >= self.SENDGRID_DAILY_MAX:
            return False, f"Global daily limit reached ({global_daily}/{self.SENDGRID_DAILY_MAX})"
        
        return True, "OK"
    
    def record_email_sent(self, client_id: int) -> int:
        """
        Record that an email was sent.
        
        Increments:
        - Client daily counter
        - Client hourly counter
        - Global daily counter
        
        Returns:
            New daily count for client
        """
        # Daily counter
        daily_key = f"client:{client_id}:emails:daily"
        daily_count = self.cache.increment_rate_limit(daily_key, ttl=86400)  # 24h TTL
        
        # Hourly counter
        hourly_key = f"client:{client_id}:emails:hourly"
        self.cache.increment_rate_limit(hourly_key, ttl=3600)  # 1h TTL
        
        # Global counter
        global_key = "sendgrid:emails:daily"
        self.cache.increment_rate_limit(global_key, ttl=86400)
        
        logger.info(f"📧 Email sent by client {client_id}. Daily: {daily_count}")
        return daily_count
    
    def get_emails_sent_today(self, client_id: int) -> int:
        """Get number of emails sent today by client."""
        return self.cache.get_rate_limit(f"client:{client_id}:emails:daily")
    
    def get_emails_sent_this_hour(self, client_id: int) -> int:
        """Get number of emails sent this hour by client."""
        return self.cache.get_rate_limit(f"client:{client_id}:emails:hourly")
    
    def get_global_emails_sent_today(self) -> int:
        """Get total emails sent today (all clients)."""
        return self.cache.get_rate_limit("sendgrid:emails:daily")
    
    # ==========================================
    # ADAPTIVE DELAYS
    # ==========================================
    
    def calculate_next_email_delay(self, client_id: int) -> int:
        """
        Calculate adaptive delay before next email.
        
        Logic:
        - Start with base delay (2 min)
        - Increase if approaching limits
        - Decrease if under 50% of limit
        - Add jitter for natural pattern
        
        Returns:
            Delay in seconds
        """
        from app.warmup import calculate_daily_limit
        from app.database import SessionLocal, Client
        
        session = SessionLocal()
        try:
            client = session.query(Client).filter(Client.id == client_id).first()
            if not client:
                return self.DEFAULT_DELAY
            
            daily_limit = calculate_daily_limit(client)
            daily_sent = self.get_emails_sent_today(client_id)
            
            # Calculate usage percentage
            usage_percent = (daily_sent / daily_limit * 100) if daily_limit > 0 else 0
            
            # Adaptive delay logic (FIX: Use class variables properly)
            if usage_percent > 90:
                # Near limit - slow down significantly
                delay = RateLimiter.MAX_DELAY_BETWEEN_EMAILS  # ← FIX
            elif usage_percent > 75:
                # Approaching limit - moderate slowdown
                delay = int(RateLimiter.DEFAULT_DELAY * 1.5)  # ← FIX
            elif usage_percent < 50:
                # Under half - can speed up
                delay = RateLimiter.MIN_DELAY_BETWEEN_EMAILS  # ← FIX
            else:
                # Normal operation
                delay = RateLimiter.DEFAULT_DELAY  # ← FIX
            
            # Add random jitter (±20%) for natural pattern
            import random
            jitter = random.randint(-int(delay * 0.2), int(delay * 0.2))
            delay = max(RateLimiter.MIN_DELAY_BETWEEN_EMAILS, delay + jitter)  # ← FIX
            
            logger.debug(f"Adaptive delay for client {client_id}: {delay}s (usage: {usage_percent:.1f}%)")
            return delay
            
        finally:
            session.close()
    
    async def wait_with_backoff(self, client_id: int, context: str = "email"):
        """
        Async wait with adaptive delay.
        
        Args:
            client_id: Client ID
            context: What we're waiting for ("email", "api", etc.)
        """
        delay = self.calculate_next_email_delay(client_id)
        logger.info(f"⏸️  [{context}] Client {client_id}: Waiting {delay}s...")
        await asyncio.sleep(delay)
    
    # ==========================================
    # API RATE LIMITS
    # ==========================================
    
    def check_api_limit(self, api_name: str) -> tuple[bool, str]:
        """
        Check if API call is allowed.
        
        Args:
            api_name: "debounce", "firecrawl", "apify"
        
        Returns:
            (allowed: bool, reason: str)
        """
        limits = {
            "debounce": self.DEBOUNCE_PER_MINUTE,
            "crawl4ai": self.CRAWL4AI_PER_MINUTE,
            "apify": self.APIFY_PER_MINUTE,
        }
        
        limit = limits.get(api_name, 10)
        key = f"api:{api_name}:per_minute"
        current = self.cache.get_rate_limit(key)
        
        if current >= limit:
            return False, f"{api_name} rate limit ({current}/{limit}/min)"
        
        return True, "OK"
    
    def record_api_call(self, api_name: str) -> int:
        """
        Record API call and return current count.
        
        Args:
            api_name: "debounce", "crawl4ai", "apify"
        
        Returns:
            Current count this minute
        """
        key = f"api:{api_name}:per_minute"
        count = self.cache.increment_rate_limit(key, ttl=60)
        logger.debug(f"📡 API call: {api_name} ({count} this minute)")
        return count
    
    async def wait_for_api_slot(self, api_name: str, max_wait: int = 60):
        """
        Wait until API call is allowed (with timeout).
        
        Args:
            api_name: API to wait for
            max_wait: Maximum seconds to wait
        
        Returns:
            True if slot obtained, False if timeout
        """
        waited = 0
        while waited < max_wait:
            allowed, reason = self.check_api_limit(api_name)
            if allowed:
                return True
            
            logger.warning(f"⏳ {api_name} rate limited. Waiting...")
            await asyncio.sleep(5)
            waited += 5
        
        logger.error(f"❌ {api_name} rate limit timeout after {max_wait}s")
        return False
    
    # ==========================================
    # STATISTICS & MONITORING
    # ==========================================
    
    def get_rate_limit_stats(self) -> Dict:
        """
        Get comprehensive rate limit statistics.
        
        Returns:
            {
                "global_daily": 45,
                "sendgrid_usage_percent": 9.0,
                "api_usage": {"debounce": 3, "crawl4ai": 1}
            }
        """
        global_daily = self.get_global_emails_sent_today()
        
        api_usage = {}
        for api in ["debounce", "crawl4ai", "apify"]:
            key = f"api:{api}:per_minute"
            api_usage[api] = self.cache.get_rate_limit(key)
        
        return {
            "global_daily_emails": global_daily,
            "sendgrid_usage_percent": round((global_daily / self.SENDGRID_DAILY_MAX) * 100, 1),
            "api_usage_per_minute": api_usage,
            "timestamp": datetime.now().isoformat()
        }
    
    def reset_client_limits(self, client_id: int):
        """
        UTILITY: Reset all limits for client (testing/debugging).
        """
        keys = [
            f"client:{client_id}:emails:daily",
            f"client:{client_id}:emails:hourly",
        ]
        
        for key in keys:
            self.cache.redis.delete(key)
        
        logger.warning(f"🗑️ Reset rate limits for client {client_id}")

# ==========================================
# GLOBAL SINGLETON
# ==========================================

rate_limiter = RateLimiter()

# Test on import
if __name__ != "__main__":
    logger.info("⚡ Rate limiter ready")

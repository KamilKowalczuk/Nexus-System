# app/cache_manager.py
"""
CACHE MANAGER - High-Level Cache Operations
Warstwa abstrakcji dla konkretnych use case'ów (email verification, scraping, etc.)
"""

import logging
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.redis_client import redis_client

logger = logging.getLogger("cache_manager")

class CacheManager:
    """
    High-level cache operations dla Headhunter Bot.
    
    Use Cases:
    1. Email verification cache (DeBounce API results)
    2. Company scraping cache (Firecrawl results)
    3. Campaign query history
    4. Rate limiting counters
    """
    
    # ==========================================
    # TTL CONFIGURATION (in seconds)
    # ==========================================
    TTL_EMAIL_VERIFICATION = 7 * 24 * 3600      # 7 days
    TTL_COMPANY_SCRAPING = 14 * 24 * 3600       # 14 days
    TTL_CAMPAIGN_HISTORY = 30 * 24 * 3600       # 30 days
    TTL_RATE_LIMIT_HOURLY = 3600                # 1 hour
    TTL_RATE_LIMIT_DAILY = 24 * 3600            # 24 hours
    TTL_API_RESPONSE = 3 * 24 * 3600            # 3 days (generic)
    
    # ==========================================
    # KEY PREFIXES (namespacing)
    # ==========================================
    PREFIX_EMAIL = "email:verified:"
    PREFIX_COMPANY = "company:scraped:"
    PREFIX_CAMPAIGN = "campaign:"
    PREFIX_RATELIMIT = "ratelimit:"
    PREFIX_API = "api:response:"
    
    def __init__(self):
        self.redis = redis_client
    
    @staticmethod
    def _hash(text: str) -> str:
        """Create short hash from text (for key names)."""
        return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]
    
    # ==========================================
    # EMAIL VERIFICATION CACHE
    # ==========================================
    
    def get_email_verification(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get cached email verification result.
        
        Returns:
            {"result": "OK", "checked_at": "2026-02-10", "api": "debounce"}
            or None if not cached
        """
        key = f"{self.PREFIX_EMAIL}{self._hash(email)}"
        return self.redis.get_json(key)
    
    def set_email_verification(self, email: str, result: str, api: str = "debounce") -> bool:
        """
        Cache email verification result.
        
        Args:
            email: Email address
            result: "OK", "INVALID", "RISKY", "UNKNOWN"
            api: Source API ("debounce", "hunter", etc.)
        
        Returns:
            True if cached successfully
        """
        key = f"{self.PREFIX_EMAIL}{self._hash(email)}"
        data = {
            "email": email,
            "result": result,
            "checked_at": datetime.now().isoformat(),
            "api": api
        }
        success = self.redis.set_json(key, data, ttl=self.TTL_EMAIL_VERIFICATION)
        
        if success:
            logger.info(f"✅ Cached email verification: {email} → {result}")
        
        return success
    
    # ==========================================
    # COMPANY SCRAPING CACHE
    # ==========================================
    
    def get_company_scraping(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get cached Firecrawl scraping result.
        
        Returns:
            {
                "domain": "example.com",
                "markdown": "...",
                "emails": [...],
                "tech_stack": [...],
                "scraped_at": "2026-02-10T08:00:00"
            }
        """
        key = f"{self.PREFIX_COMPANY}{self._hash(domain)}"
        return self.redis.get_json(key)
    
    def set_company_scraping(self, domain: str, data: Dict[str, Any]) -> bool:
        """
        Cache Firecrawl scraping result.
        
        Args:
            domain: Company domain
            data: Scraping result (markdown, emails, tech_stack, etc.)
        """
        key = f"{self.PREFIX_COMPANY}{self._hash(domain)}"
        
        # Add metadata
        cache_data = {
            "domain": domain,
            "scraped_at": datetime.now().isoformat(),
            **data
        }
        
        success = self.redis.set_json(key, cache_data, ttl=self.TTL_COMPANY_SCRAPING)
        
        if success:
            logger.info(f"✅ Cached scraping result: {domain}")
        
        return success
    
    def delete_company_scraping(self, domain: str) -> bool:
        """
        Invalidate cached scraping result (e.g., when splash screen detected).
        """
        key = f"{self.PREFIX_COMPANY}{self._hash(domain)}"
        deleted = self.redis.delete(key)
        if deleted:
            logger.info(f"🗑️ Invalidated scraping cache: {domain}")
        return bool(deleted)
    
    # ==========================================
    # CAMPAIGN QUERY HISTORY (Replace JSON files)
    # ==========================================
    
    def get_campaign_queries(self, campaign_id: int) -> List[str]:
        """
        Get list of used queries for campaign.
        
        Returns:
            ["software house warszawa", "python agency kraków", ...]
        """
        key = f"{self.PREFIX_CAMPAIGN}{campaign_id}:used_queries"
        queries = self.redis.smembers(key)
        return list(queries) if queries else []
    
    def add_campaign_queries(self, campaign_id: int, queries: List[str]) -> int:
        """
        Add new queries to campaign history.
        
        Args:
            campaign_id: Campaign ID
            queries: List of search queries to add
        
        Returns:
            Number of new queries added (duplicates ignored)
        """
        if not queries:
            return 0
        
        key = f"{self.PREFIX_CAMPAIGN}{campaign_id}:used_queries"
        
        # Normalize queries (lowercase, strip)
        normalized = [q.lower().strip() for q in queries if q.strip()]
        
        # Add to set (duplicates auto-ignored)
        count = self.redis.sadd(key, *normalized)
        
        # Set TTL if key is new
        if count > 0:
            self.redis.expire(key, self.TTL_CAMPAIGN_HISTORY)
            logger.info(f"✅ Added {count} new queries to campaign {campaign_id}")
        
        return count
    
    def is_query_used(self, campaign_id: int, query: str) -> bool:
        """
        Check if query was already used in campaign.
        
        Args:
            campaign_id: Campaign ID
            query: Search query to check
        
        Returns:
            True if query was used before
        """
        key = f"{self.PREFIX_CAMPAIGN}{campaign_id}:used_queries"
        return self.redis.sismember(key, query.lower().strip())
    
    # ==========================================
    # RATE LIMITING
    # ==========================================
    
    def increment_rate_limit(self, key_suffix: str, ttl: int = 3600) -> int:
        """
        Increment rate limit counter.
        
        Args:
            key_suffix: Unique identifier (e.g., "client:123:hourly")
            ttl: Auto-expire after N seconds
        
        Returns:
            Current count after increment
        """
        key = f"{self.PREFIX_RATELIMIT}{key_suffix}"
        count = self.redis.incr(key)
        
        if count == 1:  # First increment, set TTL
            self.redis.expire(key, ttl)
        
        return count or 0
    
    def get_rate_limit(self, key_suffix: str) -> int:
        """
        Get current rate limit count.
        
        Returns:
            Current count (0 if not set)
        """
        key = f"{self.PREFIX_RATELIMIT}{key_suffix}"
        value = self.redis.get(key)
        return int(value) if value else 0
    
    def reset_rate_limit(self, key_suffix: str) -> bool:
        """Reset rate limit counter."""
        key = f"{self.PREFIX_RATELIMIT}{key_suffix}"
        return self.redis.delete(key)
    
    def check_rate_limit(self, key_suffix: str, limit: int) -> bool:
        """
        Check if rate limit exceeded.
        
        Args:
            key_suffix: Rate limit key
            limit: Max allowed count
        
        Returns:
            True if BELOW limit (OK to proceed)
            False if EXCEEDED limit (stop!)
        """
        current = self.get_rate_limit(key_suffix)
        return current < limit
    
    # ==========================================
    # GENERIC API RESPONSE CACHE
    # ==========================================
    
    def get_api_response(self, api_name: str, identifier: str) -> Optional[Any]:
        """
        Get cached API response.
        
        Args:
            api_name: API name (e.g., "hunter", "apify")
            identifier: Unique request identifier (domain, email, etc.)
        
        Returns:
            Cached response or None
        """
        key = f"{self.PREFIX_API}{api_name}:{self._hash(identifier)}"
        return self.redis.get_json(key)
    
    def set_api_response(self, api_name: str, identifier: str, response: Any, ttl: int = None) -> bool:
        """
        Cache API response.
        
        Args:
            api_name: API name
            identifier: Unique identifier
            response: API response (will be JSON-serialized)
            ttl: Custom TTL (defaults to TTL_API_RESPONSE)
        """
        key = f"{self.PREFIX_API}{api_name}:{self._hash(identifier)}"
        ttl = ttl or self.TTL_API_RESPONSE
        
        cache_data = {
            "identifier": identifier,
            "cached_at": datetime.now().isoformat(),
            "data": response
        }
        
        return self.redis.set_json(key, cache_data, ttl=ttl)
    
    # ==========================================
    # STATISTICS & MONITORING
    # ==========================================
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics (how many keys per type).
        
        ⚠️ Expensive operation - use sparingly!
        """
        if not self.redis.is_connected():
            return {}
        
        stats = {
            "emails_cached": len(self.redis.keys(f"{self.PREFIX_EMAIL}*")),
            "companies_cached": len(self.redis.keys(f"{self.PREFIX_COMPANY}*")),
            "campaigns_tracked": len(self.redis.keys(f"{self.PREFIX_CAMPAIGN}*")),
            "rate_limiters_active": len(self.redis.keys(f"{self.PREFIX_RATELIMIT}*")),
            "api_responses_cached": len(self.redis.keys(f"{self.PREFIX_API}*")),
        }
        
        return stats
    
    def clear_all_cache(self) -> bool:
        """
        ⚠️ DANGER: Clear entire cache.
        Only for testing/development!
        """
        logger.warning("🔥 CLEARING ALL CACHE")
        return self.redis.flush_db()
    
    # ==========================================
    # WARMUP & WARMUP STATE
    # ==========================================
    
    def get_warmup_state(self, client_id: int) -> Optional[Dict[str, Any]]:
        """
        Get warmup state for client.
        
        Returns:
            {
                "current_limit": 10,
                "started_at": "2026-02-01",
                "day_number": 5
            }
        """
        key = f"warmup:client:{client_id}"
        return self.redis.get_json(key)
    
    def set_warmup_state(self, client_id: int, state: Dict[str, Any]) -> bool:
        """
        Save warmup state.
        
        Args:
            client_id: Client ID
            state: Warmup state dict
        """
        key = f"warmup:client:{client_id}"
        return self.redis.set_json(key, state, ttl=90 * 24 * 3600)  # 90 days
    
    def delete_warmup_state(self, client_id: int) -> bool:
        """Delete warmup state (when warmup complete)."""
        key = f"warmup:client:{client_id}"
        return self.redis.delete(key)

# ==========================================
# GLOBAL SINGLETON
# ==========================================

cache_manager = CacheManager()

# Test on import
if __name__ != "__main__":
    if cache_manager.redis.is_connected():
        logger.info("🎯 Cache manager ready")

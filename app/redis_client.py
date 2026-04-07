# app/redis_client.py
"""
REDIS CLIENT - Enterprise Connection Manager
Singleton pattern z connection pooling i graceful fallbacks.
"""

import os
import json
import logging
from typing import Optional, Any, List, Dict
from datetime import timedelta
import redis
from redis.connection import ConnectionPool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("redis_client")

class RedisClient:
    """
    Unified Redis wrapper z production-ready features:
    - Connection pooling
    - Auto-reconnect
    - Graceful degradation (jeśli Redis down → log warning, return None)
    - JSON serialization helpers
    """
    
    _instance = None  # Singleton
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Prevent re-initialization
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # Configuration z .env
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.db = int(os.getenv("REDIS_DB", 0))
        redis_pass = os.getenv("REDIS_PASSWORD")
        self.password = redis_pass if redis_pass and redis_pass.strip() else None
        self.socket_timeout = int(os.getenv("REDIS_SOCKET_TIMEOUT", 5))
        self.max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", 50))
        
        # Connection pool
        self.pool = ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=True,  # Auto UTF-8 decode
            socket_timeout=self.socket_timeout,
            socket_keepalive=True,
            max_connections=self.max_connections,
            health_check_interval=30  # Health check co 30s
        )
        
        # Redis client
        self.client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Establish connection z graceful fallback."""
        try:
            self.client = redis.Redis(connection_pool=self.pool)
            # Test connection
            self.client.ping()
            logger.info(f"✅ Redis connected: {self.host}:{self.port} (DB={self.db})")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            logger.warning("⚠️ Running in DEGRADED MODE (no cache)")
            self.client = None
    
    def is_connected(self) -> bool:
        """Check if Redis is alive."""
        if not self.client:
            return False
        try:
            return self.client.ping()
        except:
            return False
    
    # ==========================================
    # BASIC OPERATIONS (with fallback)
    # ==========================================
    
    def get(self, key: str) -> Optional[str]:
        """Get value. Returns None if Redis down or key missing."""
        if not self.client:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning(f"Redis GET error for '{key}': {e}")
            return None
    
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL (seconds). Returns success status."""
        if not self.client:
            return False
        try:
            if ttl:
                return self.client.setex(key, ttl, value)
            else:
                return self.client.set(key, value)
        except Exception as e:
            logger.warning(f"Redis SET error for '{key}': {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key. Returns True if deleted."""
        if not self.client:
            return False
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.warning(f"Redis DELETE error for '{key}': {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.client:
            return False
        try:
            return bool(self.client.exists(key))
        except:
            return False
    
    def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on existing key."""
        if not self.client:
            return False
        try:
            return self.client.expire(key, seconds)
        except:
            return False
    
    # ==========================================
    # JSON HELPERS (most common use case)
    # ==========================================
    
    def get_json(self, key: str) -> Optional[Any]:
        """Get JSON-decoded value."""
        value = self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in key '{key}'")
            return None
    
    def set_json(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Set JSON-encoded value."""
        try:
            value = json.dumps(data, ensure_ascii=False)
            return self.set(key, value, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON encoding error for '{key}': {e}")
            return False
    
    # ==========================================
    # SET OPERATIONS (for campaign history)
    # ==========================================
    
    def sadd(self, key: str, *values: str) -> int:
        """Add to set. Returns number of elements added."""
        if not self.client:
            return 0
        try:
            return self.client.sadd(key, *values)
        except Exception as e:
            logger.warning(f"Redis SADD error for '{key}': {e}")
            return 0
    
    def smembers(self, key: str) -> set:
        """Get all set members."""
        if not self.client:
            return set()
        try:
            return self.client.smembers(key)
        except Exception as e:
            logger.warning(f"Redis SMEMBERS error for '{key}': {e}")
            return set()
    
    def sismember(self, key: str, value: str) -> bool:
        """Check if value in set."""
        if not self.client:
            return False
        try:
            return self.client.sismember(key, value)
        except:
            return False
    
    # ==========================================
    # HASH OPERATIONS (for structured data)
    # ==========================================
    
    def hset(self, key: str, field: str, value: str) -> bool:
        """Set hash field."""
        if not self.client:
            return False
        try:
            return bool(self.client.hset(key, field, value))
        except Exception as e:
            logger.warning(f"Redis HSET error for '{key}.{field}': {e}")
            return False
    
    def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field."""
        if not self.client:
            return None
        try:
            return self.client.hget(key, field)
        except:
            return None
    
    def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields."""
        if not self.client:
            return {}
        try:
            return self.client.hgetall(key)
        except:
            return {}
    
    def hmset(self, key: str, mapping: Dict[str, str]) -> bool:
        """Set multiple hash fields."""
        if not self.client:
            return False
        try:
            return self.client.hset(key, mapping=mapping)
        except Exception as e:
            logger.warning(f"Redis HMSET error for '{key}': {e}")
            return False
    
    # ==========================================
    # COUNTER OPERATIONS (for rate limiting)
    # ==========================================
    
    def incr(self, key: str) -> Optional[int]:
        """Increment counter. Returns new value."""
        if not self.client:
            return None
        try:
            return self.client.incr(key)
        except Exception as e:
            logger.warning(f"Redis INCR error for '{key}': {e}")
            return None
    
    def decr(self, key: str) -> Optional[int]:
        """Decrement counter."""
        if not self.client:
            return None
        try:
            return self.client.decr(key)
        except:
            return None
    
    def incrby(self, key: str, amount: int) -> Optional[int]:
        """Increment by amount."""
        if not self.client:
            return None
        try:
            return self.client.incrby(key, amount)
        except:
            return None
    
    # ==========================================
    # LIST OPERATIONS (for task queues)
    # ==========================================
    
    def lpush(self, key: str, *values: str) -> int:
        """Push to list (left). Returns new length."""
        if not self.client:
            return 0
        try:
            return self.client.lpush(key, *values)
        except:
            return 0
    
    def rpop(self, key: str) -> Optional[str]:
        """Pop from list (right)."""
        if not self.client:
            return None
        try:
            return self.client.rpop(key)
        except:
            return None
    
    def llen(self, key: str) -> int:
        """Get list length."""
        if not self.client:
            return 0
        try:
            return self.client.llen(key)
        except:
            return 0
    
    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[str]:
        """Get list range."""
        if not self.client:
            return []
        try:
            return self.client.lrange(key, start, end)
        except:
            return []
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    def ping(self) -> bool:
        """Health check."""
        return self.is_connected()
    
    def flush_db(self) -> bool:
        """⚠️ DANGER: Clear entire DB (only for testing!)."""
        if not self.client:
            return False
        try:
            self.client.flushdb()
            logger.warning("🔥 Redis DB flushed (all keys deleted)")
            return True
        except:
            return False
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern. Use sparingly in production."""
        if not self.client:
            return []
        try:
            return self.client.keys(pattern)
        except:
            return []
    
    def ttl(self, key: str) -> int:
        """Get TTL for key. Returns -1 if no TTL, -2 if key missing."""
        if not self.client:
            return -2
        try:
            return self.client.ttl(key)
        except:
            return -2

# ==========================================
# GLOBAL SINGLETON INSTANCE
# ==========================================

redis_client = RedisClient()

# Quick test on import
if __name__ != "__main__":
    if redis_client.is_connected():
        logger.info("🔥 Redis client ready")
    else:
        logger.warning("⚠️ Redis unavailable - running in degraded mode")

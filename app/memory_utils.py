# app/memory_utils.py
"""
MEMORY UTILITIES - Campaign Query History
MIGRATED: JSON files → Redis SET (50x faster, thread-safe)
"""

import json
import os
import logging
from typing import List
from app.cache_manager import cache_manager

logger = logging.getLogger("memory_utils")

FILES_DIR = "files"

def load_used_queries(campaign_id: int) -> List[str]:
    """
    Ładuje listę zapytań, które już wykorzystaliśmy w kampanii.
    
    BEFORE: Czytanie z pliku JSON (10-50ms, disk I/O)
    AFTER: Redis SET (< 1ms, in-memory)
    
    AUTO-MIGRATION: Jeśli Redis pusty, ale JSON file istnieje → importuje automatycznie
    
    Args:
        campaign_id: ID kampanii
    
    Returns:
        Lista użytych zapytań (lowercase, normalized)
    """
    try:
        # Try Redis first
        queries = cache_manager.get_campaign_queries(campaign_id)
        
        # AUTO-MIGRATION: If Redis empty but JSON exists
        if not queries:
            json_queries = _load_from_json_legacy(campaign_id)
            if json_queries:
                logger.warning(f"🔄 Migrating campaign {campaign_id} from JSON to Redis...")
                cache_manager.add_campaign_queries(campaign_id, json_queries)
                logger.info(f"✅ Migrated {len(json_queries)} queries to Redis")
                return json_queries
        
        logger.debug(f"Loaded {len(queries)} queries for campaign {campaign_id}")
        return queries
        
    except Exception as e:
        logger.error(f"Error loading queries for campaign {campaign_id}: {e}")
        # Fallback: try JSON
        return _load_from_json_legacy(campaign_id)


def save_used_queries(campaign_id: int, new_queries: List[str]):
    """
    Dopisuje nowe zapytania do historii kampanii.
    
    BEFORE: Wczytaj plik → Dodaj → Zapisz plik (race conditions!)
    AFTER: Redis SADD (atomic operation, thread-safe)
    
    Args:
        campaign_id: ID kampanii
        new_queries: Lista nowych zapytań do dodania
    """
    if not new_queries:
        return
    
    try:
        count = cache_manager.add_campaign_queries(campaign_id, new_queries)
        logger.info(f"✅ Campaign {campaign_id}: Added {count} new queries to Redis")
    except Exception as e:
        logger.error(f"Error saving queries for campaign {campaign_id}: {e}")


def is_query_used(campaign_id: int, query: str) -> bool:
    """
    Sprawdza, czy zapytanie było już użyte w kampanii.
    
    NEW FUNCTION (bonus!) - szybsze niż load_used_queries() + check in list
    
    Args:
        campaign_id: ID kampanii
        query: Zapytanie do sprawdzenia
    
    Returns:
        True jeśli zapytanie było już użyte
    """
    try:
        return cache_manager.is_query_used(campaign_id, query)
    except Exception as e:
        logger.error(f"Error checking query for campaign {campaign_id}: {e}")
        return False


# ==========================================
# LEGACY JSON SUPPORT (for migration)
# ==========================================

def _get_json_file_path(campaign_id: int) -> str:
    """Returns path to legacy JSON file."""
    return os.path.join(FILES_DIR, f"campaign_{campaign_id}_history.json")


def _load_from_json_legacy(campaign_id: int) -> List[str]:
    """
    Load queries from legacy JSON file.
    Used for auto-migration only.
    """
    filepath = _get_json_file_path(campaign_id)
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            queries = json.load(f)
            logger.debug(f"Loaded {len(queries)} queries from legacy JSON")
            return queries
    except Exception as e:
        logger.error(f"Error reading legacy JSON for campaign {campaign_id}: {e}")
        return []


def migrate_all_campaigns_to_redis() -> int:
    """
    UTILITY: Migrate all JSON files to Redis.
    Run once after Redis deployment.
    
    Returns:
        Number of campaigns migrated
    """
    if not os.path.exists(FILES_DIR):
        logger.info("No legacy files directory found")
        return 0
    
    migrated_count = 0
    
    for filename in os.listdir(FILES_DIR):
        if filename.startswith("campaign_") and filename.endswith("_history.json"):
            try:
                # Extract campaign_id from filename
                campaign_id = int(filename.replace("campaign_", "").replace("_history.json", ""))
                
                # Load from JSON
                queries = _load_from_json_legacy(campaign_id)
                if queries:
                    # Save to Redis
                    count = cache_manager.add_campaign_queries(campaign_id, queries)
                    logger.info(f"✅ Migrated campaign {campaign_id}: {count} queries")
                    migrated_count += 1
                    
            except Exception as e:
                logger.error(f"Error migrating {filename}: {e}")
    
    logger.info(f"🎉 Migration complete: {migrated_count} campaigns migrated to Redis")
    return migrated_count


# ==========================================
# BACKWARD COMPATIBILITY
# ==========================================

def get_history_file(campaign_id: int) -> str:
    """
    DEPRECATED: Kept for backward compatibility.
    Now returns Redis key name instead of file path.
    """
    logger.warning("get_history_file() is deprecated - queries now stored in Redis")
    return f"campaign:{campaign_id}:used_queries"

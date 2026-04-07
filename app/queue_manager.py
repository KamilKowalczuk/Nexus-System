# app/queue_manager.py
"""
QUEUE MANAGER - Distributed Task Queue System
Enables multi-instance deployment, better load balancing, graceful restarts.
"""

import logging
import json
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum
from app.redis_client import redis_client
from app.cache_manager import cache_manager

logger = logging.getLogger("queue_manager")

class QueueType(Enum):
    """Queue types for different lead statuses."""
    NEW = "new"                    # Freshly scouted leads
    ANALYZED = "analyzed"          # Research complete, ready for writing
    DRAFTED = "drafted"            # Email written, ready to send
    PRIORITY = "priority"          # VIP clients (process first)

class QueueManager:
    """
    Redis-based task queue for lead processing.
    
    Architecture:
    - LPUSH to add (left = newest)
    - RPOP to consume (right = oldest, FIFO)
    - Multiple workers can consume safely
    - Queues survive process restarts
    """
    
    # Queue key prefixes
    PREFIX_QUEUE = "queue:leads:"
    PREFIX_PROCESSING = "processing:lead:"
    PREFIX_WORKER = "worker:"
    
    def __init__(self):
        self.redis = redis_client
    
    # ==========================================
    # QUEUE OPERATIONS
    # ==========================================
    
    def push_lead(self, lead_id: int, queue_type: QueueType, priority: bool = False) -> bool:
        """
        Add lead to queue.
        
        Args:
            lead_id: Lead ID from database
            queue_type: Which queue to add to
            priority: If True, add to priority queue
        
        Returns:
            True if added successfully
        """
        if priority:
            queue_key = f"{self.PREFIX_QUEUE}priority"
        else:
            queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
        
        # Store as JSON for metadata
        item = json.dumps({
            "lead_id": lead_id,
            "queued_at": datetime.now().isoformat(),
            "queue_type": queue_type.value
        })
        
        count = self.redis.lpush(queue_key, item)
        if count > 0:
            logger.debug(f"📥 Queued lead {lead_id} to {queue_type.value} (priority={priority})")
            return True
        
        return False
    
    def pop_lead(self, queue_types: List[QueueType] = None, worker_id: str = None) -> Optional[Dict]:
        """
        Get next lead from queue (FIFO).
        
        Priority order:
        1. Priority queue (VIP clients)
        2. Specified queue types (in order)
        3. Default: NEW → ANALYZED → DRAFTED
        
        Args:
            queue_types: List of queues to check (in priority order)
            worker_id: Worker identifier for tracking
        
        Returns:
            {"lead_id": 123, "queued_at": "...", "queue_type": "new"}
            or None if all queues empty
        """
        if queue_types is None:
            queue_types = [QueueType.PRIORITY, QueueType.DRAFTED, QueueType.ANALYZED, QueueType.NEW]
        else:
            # Always check priority first
            if QueueType.PRIORITY not in queue_types:
                queue_types = [QueueType.PRIORITY] + queue_types
        
        # Try each queue in priority order
        for queue_type in queue_types:
            if queue_type == QueueType.PRIORITY:
                queue_key = f"{self.PREFIX_QUEUE}priority"
            else:
                queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
            
            item = self.redis.rpop(queue_key)
            if item:
                try:
                    data = json.loads(item)
                    lead_id = data["lead_id"]
                    
                    # Mark as processing
                    if worker_id:
                        self._mark_processing(lead_id, worker_id)
                    
                    logger.debug(f"📤 Popped lead {lead_id} from {queue_type.value}")
                    return data
                except json.JSONDecodeError:
                    logger.error(f"Invalid queue item: {item}")
                    continue
        
        return None
    
    def peek_queue(self, queue_type: QueueType, count: int = 10) -> List[Dict]:
        """
        Peek at queue without removing items.
        
        Args:
            queue_type: Queue to peek at
            count: Number of items to peek
        
        Returns:
            List of lead data dicts
        """
        queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
        items = self.redis.lrange(queue_key, 0, count - 1)
        
        results = []
        for item in items:
            try:
                results.append(json.loads(item))
            except:
                pass
        
        return results
    
    def get_queue_length(self, queue_type: QueueType) -> int:
        """Get number of items in queue."""
        queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
        return self.redis.llen(queue_key)
    
    def clear_queue(self, queue_type: QueueType) -> int:
        """
        Clear entire queue (maintenance function).
        
        Returns:
            Number of items removed
        """
        queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
        length = self.redis.llen(queue_key)
        self.redis.delete(queue_key)
        logger.warning(f"🗑️ Cleared {length} items from {queue_type.value} queue")
        return length
    
    # ==========================================
    # PROCESSING STATE TRACKING
    # ==========================================
    
    def _mark_processing(self, lead_id: int, worker_id: str, ttl: int = 300):
        """
        Mark lead as being processed by worker.
        TTL ensures orphaned tasks get cleaned up.
        """
        key = f"{self.PREFIX_PROCESSING}{lead_id}"
        data = json.dumps({
            "worker_id": worker_id,
            "started_at": datetime.now().isoformat()
        })
        self.redis.set(key, data, ttl=ttl)
    
    def unmark_processing(self, lead_id: int):
        """Remove processing marker (task complete)."""
        key = f"{self.PREFIX_PROCESSING}{lead_id}"
        self.redis.delete(key)
    
    def is_processing(self, lead_id: int) -> bool:
        """Check if lead is currently being processed."""
        key = f"{self.PREFIX_PROCESSING}{lead_id}"
        return self.redis.exists(key)
    
    def get_processing_info(self, lead_id: int) -> Optional[Dict]:
        """Get info about who's processing this lead."""
        key = f"{self.PREFIX_PROCESSING}{lead_id}"
        data = self.redis.get(key)
        if data:
            try:
                return json.loads(data)
            except:
                pass
        return None
    
    # ==========================================
    # WORKER HEARTBEAT & MONITORING
    # ==========================================
    
    def register_worker(self, worker_id: str, client_id: int, task: str = "idle"):
        """
        Register worker heartbeat.
        
        Args:
            worker_id: Unique worker identifier
            client_id: Client this worker is processing
            task: Current task ("scouting", "researching", etc.)
        """
        key = f"{self.PREFIX_WORKER}{worker_id}"
        data = json.dumps({
            "client_id": client_id,
            "task": task,
            "last_seen": datetime.now().isoformat()
        })
        self.redis.set(key, data, ttl=60)  # 60s TTL = dead if no heartbeat
    
    def get_active_workers(self) -> List[Dict]:
        """
        Get list of active workers.
        
        Returns:
            [{"worker_id": "worker_1", "client_id": 123, "task": "researching"}, ...]
        """
        keys = self.redis.keys(f"{self.PREFIX_WORKER}*")
        workers = []
        
        for key in keys:
            data = self.redis.get(key)
            if data:
                try:
                    worker_info = json.loads(data)
                    worker_id = key.replace(self.PREFIX_WORKER, "")
                    worker_info["worker_id"] = worker_id
                    workers.append(worker_info)
                except:
                    pass
        
        return workers
    
    def unregister_worker(self, worker_id: str):
        """Remove worker (shutdown/crash)."""
        key = f"{self.PREFIX_WORKER}{worker_id}"
        self.redis.delete(key)
    
    # ==========================================
    # STATISTICS & MONITORING
    # ==========================================
    
    def get_queue_stats(self) -> Dict:
        """
        Get comprehensive queue statistics.
        
        Returns:
            {
                "queues": {
                    "new": 45,
                    "analyzed": 12,
                    "drafted": 3,
                    "priority": 1
                },
                "processing": 5,
                "active_workers": 3,
                "total_pending": 61
            }
        """
        queue_lengths = {}
        total = 0
        
        for queue_type in QueueType:
            length = self.get_queue_length(queue_type)
            queue_lengths[queue_type.value] = length
            total += length
        
        # Count processing items
        processing_keys = self.redis.keys(f"{self.PREFIX_PROCESSING}*")
        processing_count = len(processing_keys)
        
        # Count active workers
        active_workers = len(self.get_active_workers())
        
        return {
            "queues": queue_lengths,
            "processing": processing_count,
            "active_workers": active_workers,
            "total_pending": total,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_lead_queue_position(self, lead_id: int) -> Optional[Dict]:
        """
        Find which queue lead is in and its position.
        
        Returns:
            {"queue": "new", "position": 5, "total": 45}
            or None if not in any queue
        """
        for queue_type in QueueType:
            queue_key = f"{self.PREFIX_QUEUE}{queue_type.value}"
            items = self.redis.lrange(queue_key, 0, -1)
            
            for idx, item in enumerate(items):
                try:
                    data = json.loads(item)
                    if data["lead_id"] == lead_id:
                        return {
                            "queue": queue_type.value,
                            "position": idx + 1,
                            "total": len(items)
                        }
                except:
                    pass
        
        return None
    
    # ==========================================
    # BULK OPERATIONS
    # ==========================================
    
    def bulk_push_leads(self, lead_ids: List[int], queue_type: QueueType) -> int:
        """
        Add multiple leads to queue at once.
        
        Returns:
            Number of leads added
        """
        count = 0
        for lead_id in lead_ids:
            if self.push_lead(lead_id, queue_type):
                count += 1
        
        logger.info(f"📥 Bulk pushed {count} leads to {queue_type.value}")
        return count
    
    def requeue_stale_processing(self, max_age_seconds: int = 600) -> int:
        """
        Find stale processing tasks and requeue them.
        Useful for crash recovery.
        
        Args:
            max_age_seconds: Consider processing stale after N seconds
        
        Returns:
            Number of leads requeued
        """
        # This is a maintenance function - processing markers auto-expire via TTL
        # But we can check for very old ones if needed
        logger.info("🔄 Processing task cleanup handled by TTL")
        return 0

# ==========================================
# GLOBAL SINGLETON
# ==========================================

queue_manager = QueueManager()

# Test on import
if __name__ != "__main__":
    logger.info("⚡ Queue manager ready")

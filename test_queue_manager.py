# test_queue_manager.py
from app.queue_manager import queue_manager, QueueType

print("Testing Queue Manager\n")

# Add some leads to queues
for i in range(5):
    queue_manager.push_lead(1000 + i, QueueType.NEW)

queue_manager.push_lead(2000, QueueType.ANALYZED)
queue_manager.push_lead(3000, QueueType.DRAFTED, priority=True)

# Check stats
stats = queue_manager.get_queue_stats()
print("Queue Stats:")
for key, val in stats.items():
    print(f"  {key}: {val}")

# Pop from queue
print("\nPopping leads:")
for i in range(3):
    lead = queue_manager.pop_lead(worker_id="test_worker_1")
    if lead:
        print(f"  Got lead: {lead['lead_id']} from {lead['queue_type']}")
    else:
        print("  Queue empty")

# Final stats
print("\nFinal stats:")
stats = queue_manager.get_queue_stats()
print(f"  Queues: {stats['queues']}")
print(f"  Processing: {stats['processing']}")

import os
import json
from typing import List, Dict, Any

MEMORY_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(MEMORY_DIR, "semantic_db.json")

def init_memory_db():
    """Ensures memory directory and database file exist."""
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

def save_memory(memory_data: Dict[str, Any]):
    """Appends a new incident lesson-learned entry to the semantic database."""
    init_memory_db()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memories = json.load(f)
    except Exception:
        memories = []

    # Prevent duplicating exact same incident memory ID
    if any(m.get("incident_id") == memory_data.get("incident_id") for m in memories):
        return

    memories.append(memory_data)
    
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)

def retrieve_relevant_memories(service: str, alertname: str) -> List[Dict[str, Any]]:
    """Retrieves relevant incident records based on service name and alert metadata."""
    init_memory_db()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memories = json.load(f)
    except Exception:
        return []

    # Filter memories by matching service or alert name (case-insensitive keyword check)
    matched = []
    service_lower = service.lower()
    alert_lower = alertname.lower()
    
    for mem in memories:
        mem_service = mem.get("service", "").lower()
        mem_alert = mem.get("alertname", "").lower()
        
        # Exact match or substring overlap
        if service_lower in mem_service or mem_service in service_lower:
            matched.append(mem)
        elif alert_lower in mem_alert or mem_alert in alert_lower:
            matched.append(mem)
            
    return matched

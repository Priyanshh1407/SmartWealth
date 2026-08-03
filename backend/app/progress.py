"""
Thread-safe in-memory progress store.

LangGraph's checkpointer only saves state between nodes, not during
batch processing within a node. This store lets nodes publish
real-time progress that the /api/state endpoint can merge into its
response for the frontend to poll.
"""
import threading
from typing import Dict, Any, Optional, List


class ProgressStore:
    """Singleton thread-safe dict: { thread_id -> progress_data }"""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def init(self, thread_id: str, total: int = 0):
        """Call once when the graph run starts."""
        with self._lock:
            self._data[thread_id] = {
                "current_node": "starting",
                "message": "Initializing audit pipeline…",
                "processed": 0,
                "total": total,
                "completed": False,
                "errors": [],
            }

    def update(
        self,
        thread_id: str,
        *,
        current_node: Optional[str] = None,
        message: Optional[str] = None,
        processed: Optional[int] = None,
        total: Optional[int] = None,
    ):
        """Update one or more progress fields atomically."""
        with self._lock:
            entry = self._data.get(thread_id)
            if entry is None:
                return
            if current_node is not None:
                entry["current_node"] = current_node
            if message is not None:
                entry["message"] = message
            if processed is not None:
                entry["processed"] = processed
            if total is not None:
                entry["total"] = total

    def add_error(self, thread_id: str, error: str):
        """Append a non-fatal error / warning."""
        with self._lock:
            entry = self._data.get(thread_id)
            if entry is not None:
                entry["errors"].append(error)

    def complete(self, thread_id: str):
        """Mark the run as finished."""
        with self._lock:
            entry = self._data.get(thread_id)
            if entry is not None:
                entry["completed"] = True
                entry["message"] = "Audit complete."

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Return a snapshot (copy) of the progress for a thread."""
        with self._lock:
            entry = self._data.get(thread_id)
            return dict(entry) if entry else None


# Module-level singleton — import this everywhere
progress_store = ProgressStore()

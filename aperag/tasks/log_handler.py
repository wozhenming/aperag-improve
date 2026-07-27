"""DB-backed logging handler for Celery task logs.

Captures Python logging output during index tasks and persists
to the task_log table for frontend viewing.
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone

from aperag.db.ops import db_ops

FLUSH_INTERVAL = 10  # flush every N messages
BUFFER_CAPACITY = 200  # max buffer size before forced flush


class TaskLogHandler(logging.Handler):
    """Writes log records to the task_log database table.

    Uses a thread-local context so that concurrent Celery threads
    each tag their logs with the correct collection/document/index_type.
    """

    def __init__(self, level: int = logging.INFO):
        super().__init__(level)
        self._lock = threading.Lock()
        self._buffer: deque[dict] = deque()

        # Per-thread context for log enrichment
        self._context = threading.local()

    def set_context(self, collection_id: str | None, document_id: str | None, index_type: str | None):
        """Set enrichment context for the calling thread."""
        self._context.collection_id = collection_id
        self._context.document_id = document_id
        self._context.index_type = index_type

    def clear_context(self):
        """Clear context and flush remaining logs for the calling thread."""
        self.flush()
        self._context.collection_id = None
        self._context.document_id = None
        self._context.index_type = None

    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                "collection_id": getattr(self._context, "collection_id", None),
                "document_id": getattr(self._context, "document_id", None),
                "index_type": getattr(self._context, "index_type", None),
                "level": record.levelname,
                "message": self.format(record),
                "created_at": datetime.now(timezone.utc),
            }

            with self._lock:
                self._buffer.append(entry)
                if len(self._buffer) >= BUFFER_CAPACITY:
                    self._flush_locked()

                # Also flush periodically to keep latency low
                if len(self._buffer) % FLUSH_INTERVAL == 0:
                    self._flush_locked()

        except Exception:
            self.handleError(record)

    def flush(self):
        """Flush all buffered entries to the database."""
        with self._lock:
            self._flush_locked()

    def _flush_locked(self):
        """Must be called with _lock held."""
        if not self._buffer:
            return

        entries = list(self._buffer)
        self._buffer.clear()

        try:
            db_ops.bulk_insert_task_logs(entries)
        except Exception:
            # Don't let log handler failures crash the task
            pass

    def close(self):
        self.flush()
        super().close()


# Singleton instance
task_log_handler = TaskLogHandler()

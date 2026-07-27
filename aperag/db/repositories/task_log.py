# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from sqlalchemy import delete, select

from aperag.db import models as db_models
from aperag.db.repositories.base import SyncRepositoryProtocol


class TaskLogRepositoryMixin(SyncRepositoryProtocol):
    """Sync repository mixin for task_log operations."""

    def bulk_insert_task_logs(self, entries: list[dict]):
        """Insert multiple log entries in a single transaction."""
        def _operation(session):
            for entry in entries:
                log = db_models.TaskLog(
                    collection_id=entry.get("collection_id"),
                    document_id=entry.get("document_id"),
                    index_type=entry.get("index_type"),
                    level=entry.get("level"),
                    message=entry.get("message"),
                )
                session.add(log)
        self._execute_transaction(_operation)

    def query_task_logs(
        self,
        collection_id: str | None = None,
        document_id: str | None = None,
        index_type: str | None = None,
        limit: int = 200,
        before_id: int | None = None,
    ) -> list[db_models.TaskLog]:
        """Query task logs with optional filters."""
        def _query(session):
            stmt = select(db_models.TaskLog)
            if collection_id:
                stmt = stmt.where(db_models.TaskLog.collection_id == collection_id)
            if document_id:
                stmt = stmt.where(db_models.TaskLog.document_id == document_id)
            if index_type:
                stmt = stmt.where(db_models.TaskLog.index_type == index_type)
            if before_id:
                stmt = stmt.where(db_models.TaskLog.id < before_id)
            stmt = stmt.order_by(db_models.TaskLog.id.desc()).limit(limit)
            result = session.execute(stmt)
            return result.scalars().all()
        return self._execute_query(_query)

    def cleanup_old_task_logs(self, before_days: int = 7) -> int:
        """Delete log entries older than before_days. Returns count deleted."""
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=before_days)

        def _operation(session):
            stmt = delete(db_models.TaskLog).where(db_models.TaskLog.created_at < cutoff)
            result = session.execute(stmt)
            return result.rowcount
        return self._execute_transaction(_operation)

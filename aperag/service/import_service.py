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

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, select

from aperag.db.models import ImportTask, ImportTaskStatus
from aperag.db.ops import async_db_ops
from aperag.schema import view_models

logger = logging.getLogger(__name__)

MAX_CONCURRENT_IMPORT_TASKS = 3


class ImportService:
    def __init__(self):
        self.db_ops = async_db_ops

    async def create_import_task(
        self, user_id: str, zip_path: str, collection_title: str,
        target_embedding_model: str = "", target_completion_model: str = "",
        export_type: str = "basic",
        target_embedding_provider: str = "", target_embedding_custom_provider: str = "",
        target_completion_provider: str = "", target_completion_custom_provider: str = "",
    ) -> view_models.ImportTaskResponse:
        from sqlalchemy import func

        async def _create(session):
            # Check concurrent task limit
            running_count = await session.execute(
                select(func.count()).where(
                    and_(
                        ImportTask.user == user_id,
                        ImportTask.status.in_([ImportTaskStatus.PENDING, ImportTaskStatus.PROCESSING]),
                    )
                )
            )
            if running_count.scalar() >= MAX_CONCURRENT_IMPORT_TASKS:
                raise HTTPException(status_code=429, detail="Too many concurrent import tasks.")

            task = ImportTask(
                id=f"import{uuid.uuid4().hex[:16]}",
                user=user_id,
                collection_title=collection_title,
                zip_path=zip_path,
                status=ImportTaskStatus.PENDING,
                progress=0,
                message="Import task created, waiting to start...",
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

        task = await self.db_ops._execute_query(_create)

        from config.import_tasks import import_collection_task

        import_collection_task.delay(
            import_task_id=str(task.id),
            target_embedding_model=target_embedding_model,
            target_embedding_provider=target_embedding_provider,
            target_embedding_custom_provider=target_embedding_custom_provider,
            target_completion_model=target_completion_model,
            target_completion_provider=target_completion_provider,
            target_completion_custom_provider=target_completion_custom_provider,
            export_type=export_type,
        )

        return view_models.ImportTaskResponse(
            task_id=str(task.id),
            status=task.status,
            progress=task.progress,
            message=task.message,
        )

    async def get_import_task(self, user_id: str, task_id: str) -> view_models.ImportTaskResponse:
        async def _get(session):
            result = await session.execute(
                select(ImportTask).where(and_(ImportTask.id == task_id, ImportTask.user == user_id))
            )
            return result.scalars().first()

        task = await self.db_ops._execute_query(_get)
        if task is None:
            raise HTTPException(status_code=404, detail="Import task not found")

        return view_models.ImportTaskResponse(
            task_id=str(task.id),
            status=task.status,
            progress=task.progress,
            message=task.message,
            error_message=task.error_message,
            collection_id=task.collection_id,
            collection_title=task.collection_title,
        )

    async def continue_import_task(
        self, user_id: str, task_id: str, action: str
    ) -> view_models.ImportTaskResponse:
        async def _get(session):
            result = await session.execute(
                select(ImportTask).where(and_(ImportTask.id == task_id, ImportTask.user == user_id))
            )
            return result.scalars().first()

        task = await self.db_ops._execute_query(_get)
        if task is None:
            raise HTTPException(status_code=404, detail="Import task not found")

        if action == "cancel":
            async def _cancel(session):
                t = await session.get(ImportTask, task.id)
                if t and t.collection_id:
                    # Clean up the partially created collection
                    from sqlalchemy import delete

                    from aperag.db.models import Collection, Document, DocumentIndex

                    cid = t.collection_id
                    await session.execute(delete(DocumentIndex).where(DocumentIndex.document_id.in_(
                        select(Document.id).where(Document.collection_id == cid)
                    )))
                    await session.execute(delete(Document).where(Document.collection_id == cid))
                    await session.execute(delete(Collection).where(Collection.id == cid))
                    t.collection_id = None
                if t:
                    t.status = ImportTaskStatus.FAILED
                    t.message = "Import cancelled by user."
                    session.commit()

            await self.db_ops._execute_query(_cancel)
            return view_models.ImportTaskResponse(
                task_id=str(task.id),
                status="CANCELLED",
                message="Import cancelled.",
            )

        if action == "reindex":
            from config.import_tasks import import_collection_reindex_task

            async def _start(session):
                t = await session.get(ImportTask, task.id)
                if t:
                    t.status = ImportTaskStatus.PROCESSING
                    t.message = "Import: re-indexing with target embedding model..."
                    t.progress = 55
                    session.commit()

            await self.db_ops._execute_query(_start)
            import_collection_reindex_task.delay(import_task_id=str(task.id))
            return view_models.ImportTaskResponse(
                task_id=str(task.id),
                status="PROCESSING",
                progress=55,
                message="Re-indexing with target model...",
            )

        if action == "force":
            from config.import_tasks import import_collection_force_continue_task

            async def _start(session):
                t = await session.get(ImportTask, task.id)
                if t:
                    t.status = ImportTaskStatus.PROCESSING
                    t.message = "Import: force importing with mismatched vectors..."
                    t.progress = 55
                    session.commit()

            await self.db_ops._execute_query(_start)
            import_collection_force_continue_task.delay(import_task_id=str(task.id))
            return view_models.ImportTaskResponse(
                task_id=str(task.id),
                status="PROCESSING",
                progress=55,
                message="Force importing with original vectors (may not work correctly)...",
            )

        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


import_service = ImportService()

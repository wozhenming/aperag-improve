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

from fastapi import APIRouter, Depends

from aperag.db.models import User
from aperag.db.ops import db_ops
from aperag.schema.view_models import TaskLogListResponse, TaskLogResponse
from aperag.views.auth import required_user

router = APIRouter()


@router.get("/logs", tags=["Logs"])
async def get_task_logs(
    collection_id: str | None = None,
    document_id: str | None = None,
    index_type: str | None = None,
    limit: int = 200,
    before_id: int | None = None,
    user: User = Depends(required_user),
) -> TaskLogListResponse:
    """Query Celery task logs filtered by collection, document, or index type.

    Returned in reverse chronological order (newest first).
    """
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000

    # Fetch one extra to determine has_more
    fetch_limit = limit + 1
    rows = db_ops.query_task_logs(
        collection_id=collection_id,
        document_id=document_id,
        index_type=index_type,
        limit=fetch_limit,
        before_id=before_id,
    )

    has_more = len(rows) == fetch_limit
    if has_more:
        rows = rows[:limit]

    logs = [
        TaskLogResponse(
            id=row.id,
            collection_id=row.collection_id,
            document_id=row.document_id,
            index_type=row.index_type,
            level=row.level,
            message=row.message,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]

    return TaskLogListResponse(logs=logs, total=len(logs), has_more=has_more)

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
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile

from aperag.db.models import User
from aperag.schema import view_models
from aperag.views.auth import required_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/collections/import",
    tags=["import"],
    status_code=202,
    operation_id="import_collection",
)
async def import_collection_view(
    request: Request,
    file: UploadFile,
    collection_title: str = Form("Imported Collection"),
    user: User = Depends(required_user),
) -> view_models.ImportTaskResponse:
    """Upload a ZIP file exported from ApeRAG to import a knowledge base."""
    from aperag.service.import_service import import_service

    # Save uploaded file to temp location
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".zip"
    temp_path = os.path.join(tempfile.gettempdir(), f"import_{uuid.uuid4().hex}{suffix}")
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception:
        raise ValueError("Failed to save uploaded file")

    return await import_service.create_import_task(
        str(user.id), temp_path, collection_title
    )


@router.get(
    "/import-tasks/{task_id}",
    tags=["import"],
    operation_id="get_import_task",
)
async def get_import_task_view(
    request: Request,
    task_id: str,
    user: User = Depends(required_user),
) -> view_models.ImportTaskResponse:
    """Query the status and progress of an import task."""
    from aperag.service.import_service import import_service

    return await import_service.get_import_task(str(user.id), task_id)

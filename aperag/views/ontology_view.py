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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from aperag.db.models import User
from aperag.schema import view_models
from aperag.service.ontology_service import ontology_service
from aperag.views.auth import required_user

router = APIRouter()


@router.get("/ontologies", tags=["Ontology"])
async def list_ontologies(request: Request, user: User = Depends(required_user)) -> view_models.OntologyList:
    items = await ontology_service.list_ontologies(str(user.id))
    return view_models.OntologyList(items=items)


@router.post("/ontologies", tags=["Ontology"])
async def create_ontology(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    user: User = Depends(required_user),
) -> view_models.Ontology:
    return await ontology_service.create_ontology(str(user.id), file, title)


@router.get("/ontologies/{ontology_id}", tags=["Ontology"])
async def get_ontology(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
) -> view_models.Ontology:
    ontology = await ontology_service.get_ontology(str(user.id), ontology_id)
    if not ontology:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return ontology


@router.delete("/ontologies/{ontology_id}", tags=["Ontology"])
async def delete_ontology(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    deleted = await ontology_service.delete_ontology(str(user.id), ontology_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return {"success": True}


@router.post("/ontologies/bot/session", tags=["Ontology"])
async def get_ontology_bot_session(
    request: Request,
    user: User = Depends(required_user),
) -> view_models.OntologyBotSession:
    """Get or create the Ontology Engineer bot + a fresh chat for guided OWL generation."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        bot = await ontology_service.get_or_create_ontology_bot(str(user.id))
        logger.info(f"ontology bot: {bot.id}")

        from aperag.service.chat_service import chat_service_global

        chat = await chat_service_global.create_chat(str(user.id), bot.id)
        logger.info(f"ontology chat: {chat.id}")
        return view_models.OntologyBotSession(bot_id=bot.id, chat_id=chat.id)
    except Exception as e:
        logger.error(f"ontology bot session failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

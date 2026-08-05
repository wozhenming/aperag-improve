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
    file: UploadFile | None = File(None),
    title: str | None = Form(None),
    user: User = Depends(required_user),
) -> view_models.Ontology:
    """Create an ontology. Pass a .owl file to import one, or omit the file to
    create a blank ontology (built from scratch in the visual editor)."""
    if file is None and not (title and title.strip()):
        raise HTTPException(status_code=400, detail="file or title is required")
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


@router.get("/ontologies/{ontology_id}/content", tags=["Ontology"])
async def get_ontology_content(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    title, content = await ontology_service.get_ontology_content(str(user.id), ontology_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return {"title": title, "content": content}


@router.put("/ontologies/{ontology_id}/content", tags=["Ontology"])
async def update_ontology_content(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    body = await request.json()
    content = (body or {}).get("content")
    title = (body or {}).get("title")
    if content:
        ok = await ontology_service.update_ontology_content(str(user.id), ontology_id, content)
        if not ok:
            raise HTTPException(status_code=404, detail="Ontology not found")
    if title:
        ok = await ontology_service.update_ontology_meta(str(user.id), ontology_id, title)
        if not ok:
            raise HTTPException(status_code=404, detail="Ontology not found")
    if not content and not title:
        raise HTTPException(status_code=400, detail="content or title is required")
    return {"success": True}


@router.post("/ontologies/parse", tags=["Ontology"])
async def parse_ontology_content(
    request: Request,
    user: User = Depends(required_user),
):
    """Parse arbitrary OWL text and return its structure (used for live preview while
    editing the raw source)."""
    body = await request.json()
    content = (body or {}).get("content")
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="content is required")
    return ontology_service.parse_owl_content(content)


@router.post("/ontologies/{ontology_id}/rebuild", tags=["Ontology"])
async def rebuild_ontology(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    """Regenerate the .owl file from an edited structure dict (visual editor save)."""
    body = await request.json() or {}
    structure = body.get("structure")
    if not structure:
        raise HTTPException(status_code=400, detail="structure is required")
    ok, content = await ontology_service.rebuild_ontology(str(user.id), ontology_id, structure, title=body.get("title"))
    if not ok:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return {"content": content}


@router.get("/ontologies/{ontology_id}/structure", tags=["Ontology"])
async def get_ontology_structure(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    """Parse the .owl file and return its full structure (classes, object/data properties)."""
    structure = await ontology_service.get_ontology_structure(str(user.id), ontology_id)
    if structure is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return structure


@router.get("/ontologies/{ontology_id}/download", tags=["Ontology"])
async def download_ontology(
    request: Request,
    ontology_id: str,
    user: User = Depends(required_user),
):
    """Download the .owl file for an ontology."""
    from fastapi.responses import Response

    title, content = await ontology_service.get_ontology_content(str(user.id), ontology_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    filename = f"{title or 'ontology'}.owl"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    title: str | None = Form(None),
) -> view_models.OntologyBotSession:
    """Get or create the Ontology Engineer bot + a fresh chat for guided OWL generation."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        bot = await ontology_service.get_or_create_ontology_bot(str(user.id))
        logger.info(f"ONTOLOGY-SESSION bot: {bot.id}")

        from aperag.service.chat_service import chat_service_global

        chat = await chat_service_global.create_chat(str(user.id), bot.id, category="ontology")
        if title and title.strip():
            await chat_service_global.update_chat(
                str(user.id),
                bot.id,
                chat.id,
                view_models.ChatUpdate(title=title.strip()[:100]),
            )
        logger.info(f"ONTOLOGY-SESSION chat: {chat.id}")
        return view_models.OntologyBotSession(bot_id=bot.id, chat_id=chat.id)
    except Exception as e:
        logger.error(f"ontology bot session failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

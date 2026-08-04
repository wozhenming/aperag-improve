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

"""Ontology library service — user-level OWL storage, CRUD, and the Ontology Engineer bot."""

import logging
from typing import Optional

from fastapi import UploadFile

from aperag.db import models as db_models
from aperag.db.ops import AsyncDatabaseOps, async_db_ops
from aperag.schema import view_models

logger = logging.getLogger(__name__)

ONTOLOGY_BOT_TITLE = "Ontology Engineer"
ONTOLOGY_BOT_DESCRIPTION = "AI ontology engineer that guides you step-by-step to build OWL ontologies."


class OntologyService:
    def __init__(self, db_ops: AsyncDatabaseOps = async_db_ops):
        self.db_ops = db_ops

    async def _to_view(self, row: db_models.Ontology) -> view_models.Ontology:
        preview = None
        if row.file_path:
            try:
                import tempfile

                from aperag.objectstore.base import get_object_store
                from aperag.ontology.parser import parse_owl

                store = get_object_store()
                content = store.get(row.file_path)
                if hasattr(content, "read"):
                    content = content.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                with tempfile.NamedTemporaryFile(suffix=".owl", delete=False, mode="w", encoding="utf-8") as tmp:
                    tmp.write(content)
                    tmp.flush()
                    schema = parse_owl(tmp.name)
                if schema and not schema.is_empty():
                    preview = {
                        "classes_count": len(schema.classes),
                        "classes": [
                            {"name": n, "label": schema.class_labels.get(n), "parents": schema.class_hierarchy.get(n, [])}
                            for n in schema.classes[:50]
                        ],
                        "object_properties_count": len(set(name for _, name, _ in schema.object_properties)),
                        "object_properties": list(set(name for _, name, _ in schema.object_properties))[:50],
                        "data_properties_count": sum(len(v) for v in schema.data_properties.values()),
                        "data_properties": {
                            cls: [{"name": p.name, "label": p.label, "range": p.range_} for p in props[:20]]
                            for cls, props in list(schema.data_properties.items())[:10]
                        },
                    }
            except Exception as e:
                logger.warning(f"Ontology preview parse failed for {row.id}: {e}")

        return view_models.Ontology(
            id=row.id,
            title=row.title,
            description=row.description,
            file_path=row.file_path,
            status=row.status,
            preview=preview,
            created=row.gmt_created,
            updated=row.gmt_updated,
        )

    async def create_ontology(self, user_id: str, file: UploadFile, title: str | None = None) -> view_models.Ontology:
        """Store an uploaded .owl file and create an ontology library entry."""
        content = await file.read()
        filename = file.filename or "ontology.owl"
        safe_user = str(user_id).replace("|", "-")
        obj_path = f"user-{safe_user}/ontology/{filename}"

        from aperag.objectstore.base import get_async_object_store

        store = get_async_object_store()
        await store.put(obj_path, content)

        final_title = title or filename.rsplit(".", 1)[0]

        async def _create(session):
            row = db_models.Ontology(
                user=user_id, title=final_title, file_path=obj_path, status="ACTIVE"
            )
            session.add(row)
            await session.flush()
            return row

        row = await self.db_ops.execute_with_transaction(_create)
        return await self._to_view(row)

    async def list_ontologies(self, user_id: str) -> list[view_models.Ontology]:
        async def _query(session):
            from sqlalchemy import select

            stmt = (
                select(db_models.Ontology)
                .where(
                    db_models.Ontology.user == user_id,
                    db_models.Ontology.status == "ACTIVE",
                    db_models.Ontology.gmt_deleted.is_(None),
                )
                .order_by(db_models.Ontology.gmt_created.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

        rows = await self.db_ops._execute_query(_query)
        return [await self._to_view(r) for r in rows]

    async def get_ontology(self, user_id: str, ontology_id: str) -> Optional[view_models.Ontology]:
        async def _query(session):
            from sqlalchemy import select

            stmt = select(db_models.Ontology).where(
                db_models.Ontology.id == ontology_id,
                db_models.Ontology.user == user_id,
                db_models.Ontology.status == "ACTIVE",
                db_models.Ontology.gmt_deleted.is_(None),
            )
            result = await session.execute(stmt)
            return result.scalars().first()

        row = await self.db_ops._execute_query(_query)
        return await self._to_view(row) if row else None

    async def delete_ontology(self, user_id: str, ontology_id: str) -> bool:
        async def _operation(session):
            from sqlalchemy import select

            stmt = select(db_models.Ontology).where(
                db_models.Ontology.id == ontology_id,
                db_models.Ontology.user == user_id,
                db_models.Ontology.status == "ACTIVE",
                db_models.Ontology.gmt_deleted.is_(None),
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            if not row:
                return False
            from aperag.utils.utils import utc_now

            row.status = "DELETED"
            row.gmt_deleted = utc_now()
            await session.flush()
            return True

        return await self.db_ops.execute_with_transaction(_operation)

    async def get_or_create_ontology_bot(self, user_id: str) -> view_models.Bot:
        """Find or create the Ontology Engineer bot for this user."""
        from sqlalchemy import select

        # Look for existing bot
        async def _find(session):
            stmt = (
                select(db_models.Bot)
                .where(
                    db_models.Bot.user == user_id,
                    db_models.Bot.title == ONTOLOGY_BOT_TITLE,
                    db_models.Bot.status == db_models.BotStatus.ACTIVE,
                )
                .order_by(db_models.Bot.gmt_created.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

        existing = await self.db_ops._execute_query(_find)
        if existing:
            import json as _json

            config_val: view_models.BotConfig | None = None
            raw = existing.config
            if raw:
                try:
                    raw_dict = _json.loads(raw) if isinstance(raw, str) else raw
                    config_val = view_models.BotConfig(**raw_dict)
                except Exception:
                    config_val = None
            return view_models.Bot(
                id=existing.id, title=existing.title, description=existing.description,
                type=existing.type.value if hasattr(existing.type, "value") else str(existing.type),
                config=config_val,
                created=existing.gmt_created, updated=existing.gmt_updated,
            )

        # Create the Ontology Engineer bot
        from aperag.ontology.prompt import ONTOLOGY_ENGINEER_SYSTEM_PROMPT

        agent_config = view_models.Agent(
            system_prompt_template=ONTOLOGY_ENGINEER_SYSTEM_PROMPT,
            tools_enabled=False,
            collections=[],
        )
        bot_config = view_models.BotConfig(agent=agent_config)
        bot_create = view_models.BotCreate(
            title=ONTOLOGY_BOT_TITLE,
            description=ONTOLOGY_BOT_DESCRIPTION,
            type=db_models.BotType.AGENT,
            config=bot_config,
        )

        from aperag.service.bot_service import bot_service

        bot = await bot_service.create_bot(user=str(user_id), bot_in=bot_create, skip_quota_check=True)
        return bot


ontology_service = OntologyService()

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

    def _parse_schema_content(self, content: str):
        """Parse OWL XML content into an OntologySchema (RDFLib, via temp file)."""
        import os
        import tempfile

        from aperag.ontology.parser import parse_owl

        with tempfile.NamedTemporaryFile(suffix=".owl", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            try:
                return parse_owl(tmp.name)
            finally:
                os.unlink(tmp.name)

    async def _to_view(self, row: db_models.Ontology) -> view_models.Ontology:
        preview = None
        if row.file_path:
            try:
                from aperag.objectstore.base import get_object_store

                store = get_object_store()
                content = store.get(row.file_path)
                if hasattr(content, "read"):
                    content = content.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                schema = self._parse_schema_content(content)
                if schema and not schema.is_empty():
                    preview = {
                        "classes_count": len(schema.classes),
                        "classes": [
                            {
                                "name": n,
                                "label": schema.class_labels.get(n),
                                "parents": schema.class_hierarchy.get(n, []),
                            }
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

    async def create_ontology(
        self, user_id: str, file: UploadFile | None = None, title: str | None = None
    ) -> view_models.Ontology:
        """Store an uploaded .owl file and create an ontology library entry.

        If `file` is None, create a blank ontology (empty structure) that the
        user builds from scratch in the visual editor.
        """
        from aperag.ontology.generator import structure_to_owl

        if file is not None:
            content = await file.read()
            filename = file.filename or "ontology.owl"
        else:
            # Blank ontology — canonical OWL with just an empty structure
            content = structure_to_owl(
                {"classes": [], "object_properties": [], "data_properties": {}}
            ).encode("utf-8")
            safe_title = (title or "ontology").strip()[:50] or "ontology"
            filename = f"{safe_title}.owl"

        safe_user = str(user_id).replace("|", "-")
        obj_path = f"user-{safe_user}/ontology/{filename}"

        from aperag.objectstore.base import get_async_object_store

        store = get_async_object_store()
        await store.put(obj_path, content)

        final_title = title or filename.rsplit(".", 1)[0]

        async def _create(session):
            row = db_models.Ontology(user=user_id, title=final_title, file_path=obj_path, status="ACTIVE")
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

    async def get_ontology_content(self, user_id: str, ontology_id: str) -> tuple[str | None, str | None]:
        """Return (title, owl_content) for editing."""

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
        if not row or not row.file_path:
            return None, None
        from aperag.objectstore.base import get_object_store

        content = get_object_store().get(row.file_path)
        if hasattr(content, "read"):
            content = content.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return row.title, content

    def _schema_to_structure(self, schema) -> dict:
        """Convert a parsed OntologySchema into the frontend structure dict
        (classes with labels/comments/parents, object properties with domain/range,
        data properties). Used by the edit page to render the graph and by the
        visual editor to edit the ontology."""
        classes_info = []
        for name in schema.classes[:1000]:
            info = {"name": name}
            if name in schema.class_labels:
                info["label"] = schema.class_labels[name]
            if name in schema.class_comments:
                info["comment"] = schema.class_comments[name]
            if name in schema.class_hierarchy:
                info["parents"] = schema.class_hierarchy[name]
            classes_info.append(info)

        obj_props_info = []
        seen = set()
        for _, name, _ in schema.object_properties:
            if name in seen:
                continue
            seen.add(name)
            detail = schema.obj_prop_details.get(name)
            entry = {"name": name}
            if detail:
                if detail.label:
                    entry["label"] = detail.label
                if detail.comment:
                    entry["comment"] = detail.comment
                if detail.domain:
                    entry["domain"] = detail.domain
                if detail.range_:
                    entry["range"] = detail.range_
                if detail.inverse:
                    entry["inverse"] = detail.inverse
            obj_props_info.append(entry)

        dp_info: dict[str, list[dict]] = {}
        for cls, props in list(schema.data_properties.items())[:200]:
            dp_info[cls] = [
                {
                    "name": p.name,
                    "label": p.label,
                    "comment": p.comment,
                    "range": p.range_,
                    "functional": p.functional,
                }
                for p in props[:200]
            ]

        return {
            "classes_count": len(schema.classes),
            "classes": classes_info,
            "object_properties_count": len(obj_props_info),
            "object_properties": obj_props_info,
            "data_properties_count": sum(len(v) for v in schema.data_properties.values()),
            "data_properties": dp_info,
            "disjoint_pairs": schema.disjoint_pairs[:50],
        }

    async def get_ontology_structure(self, user_id: str, ontology_id: str) -> Optional[dict]:
        """Parse the .owl file and return its full structure — used by the edit page."""
        title, content = await self.get_ontology_content(user_id, ontology_id)
        if content is None:
            return None
        return self.parse_owl_content(content)

    def parse_owl_content(self, content: str) -> dict:
        """Parse arbitrary OWL text and return the structure dict, or {"error": ...}."""
        try:
            schema = self._parse_schema_content(content)
        except Exception as e:
            logger.warning(f"OWL structure parse failed: {e}")
            return {"error": str(e)}
        if not schema or schema.is_empty():
            return {"error": "empty"}
        return self._schema_to_structure(schema)

    async def rebuild_ontology(
        self,
        user_id: str,
        ontology_id: str,
        structure: dict,
        title: str | None = None,
    ) -> tuple[bool, str | None]:
        """Regenerate the .owl file from an edited structure dict (canonical form)
        and return the new content. Optionally updates the title."""
        from aperag.ontology.generator import structure_to_owl

        content = structure_to_owl(structure)

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
            if not row or not row.file_path:
                return None
            if title and title.strip():
                row.title = title.strip()[:100]
            await session.flush()
            return row.file_path

        file_path = await self.db_ops.execute_with_transaction(_operation)
        if not file_path:
            return False, None
        from aperag.objectstore.base import get_object_store

        get_object_store().put(file_path, content.encode("utf-8"))
        return True, content

    async def update_ontology_content(self, user_id: str, ontology_id: str, content: str) -> bool:
        """Overwrite the .owl file for an ontology."""

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
        if not row or not row.file_path:
            return False
        from aperag.objectstore.base import get_object_store

        get_object_store().put(row.file_path, content.encode("utf-8"))
        return True

    async def update_ontology_meta(self, user_id: str, ontology_id: str, title: str | None = None) -> bool:
        """Update ontology metadata (title)."""

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
            if title:
                row.title = title.strip()[:100]
            await session.flush()
            return True

        return await self.db_ops.execute_with_transaction(_operation)

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
            # Ensure the existing bot has the latest ontology-engineer prompts
            import json as _json

            from aperag.ontology.prompt import (
                ONTOLOGY_ENGINEER_QUERY_PROMPT,
                ONTOLOGY_ENGINEER_SYSTEM_PROMPT,
            )

            raw_config = existing.config or "{}"
            try:
                cfg_dict = _json.loads(raw_config) if isinstance(raw_config, str) else raw_config
            except Exception:
                cfg_dict = {}
            agent = cfg_dict.setdefault("agent", {})
            changed = False
            if agent.get("system_prompt_template") != ONTOLOGY_ENGINEER_SYSTEM_PROMPT:
                agent["system_prompt_template"] = ONTOLOGY_ENGINEER_SYSTEM_PROMPT
                changed = True
            if agent.get("query_prompt_template") != ONTOLOGY_ENGINEER_QUERY_PROMPT:
                agent["query_prompt_template"] = ONTOLOGY_ENGINEER_QUERY_PROMPT
                changed = True
            if agent.get("tools_enabled") is not False:
                agent["tools_enabled"] = False
                changed = True
            if changed:
                await self.db_ops.update_bot_config_by_id(str(user_id), existing.id, _json.dumps(cfg_dict))
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
                id=existing.id,
                title=existing.title,
                description=existing.description,
                type=existing.type.value if hasattr(existing.type, "value") else str(existing.type),
                config=config_val,
                created=existing.gmt_created,
                updated=existing.gmt_updated,
            )

        # Create the Ontology Engineer bot
        from aperag.ontology.prompt import ONTOLOGY_ENGINEER_QUERY_PROMPT, ONTOLOGY_ENGINEER_SYSTEM_PROMPT

        agent_config = view_models.Agent(
            system_prompt_template=ONTOLOGY_ENGINEER_SYSTEM_PROMPT,
            query_prompt_template=ONTOLOGY_ENGINEER_QUERY_PROMPT,
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

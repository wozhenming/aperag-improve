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

import json
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from aperag.config import settings as config_settings
from aperag.db.ops import AsyncDatabaseOps, async_db_ops, db_ops


class SettingService:
    """Service for handling global settings"""

    def __init__(self, session: AsyncSession = None):
        if session is None:
            self.db_ops = async_db_ops
        else:
            self.db_ops = AsyncDatabaseOps(session)

    async def get_setting(self, key: str) -> Any | None:
        setting = await self.db_ops.query_setting(key)
        if not setting or setting.value is None:
            return None
        return json.loads(setting.value)

    async def update_setting(self, key: str, value: Any):
        await self.db_ops.update_setting(key, json.dumps(value))

    async def get_mineru_api_token(self) -> str | None:
        return await self.get_setting("mineru_api_token")

    async def update_mineru_api_token(self, token: str):
        await self.update_setting("mineru_api_token", token)

    async def get_use_mineru(self) -> bool:
        return await self.get_setting("use_mineru") or False

    async def update_use_mineru(self, use_mineru: bool):
        await self.update_setting("use_mineru", use_mineru)

    async def get_use_doc_ray(self) -> bool:
        return await self.get_setting("use_doc_ray") or False

    async def update_use_doc_ray(self, use_doc_ray: bool):
        await self.update_setting("use_doc_ray", use_doc_ray)

    async def get_use_markitdown(self) -> bool:
        return await self.get_setting("use_markitdown") or True

    async def update_use_markitdown(self, use_markitdown: bool):

        await self.update_setting("use_markitdown", use_markitdown)

    async def get_paddleocr_host(self) -> str:
        val = await self.get_setting("paddleocr_host")
        return val or ""

    def get_paddleocr_host_sync(self) -> str:
        val = self.get_all_settings_sync().get("paddleocr_host")
        return val or ""

    async def get_whisper_host(self) -> str:
        val = await self.get_setting("whisper_host")
        return val or ""

    def get_whisper_host_sync(self) -> str:
        val = self.get_all_settings_sync().get("whisper_host")
        return val or ""

    # ── Core chunking configuration ──────────────────────────────────────

    async def get_chunk_size(self) -> int:
        val = await self.get_setting("chunk_size")
        return val if val is not None else config_settings.chunk_size

    def get_chunk_size_sync(self) -> int:
        settings_dict = self.get_all_settings_sync()
        val = settings_dict.get("chunk_size")
        return val if val is not None else config_settings.chunk_size

    async def get_chunk_overlap_size(self) -> int:
        val = await self.get_setting("chunk_overlap_size")
        return val if val is not None else config_settings.chunk_overlap_size

    def get_chunk_overlap_size_sync(self) -> int:
        settings_dict = self.get_all_settings_sync()
        val = settings_dict.get("chunk_overlap_size")
        return val if val is not None else config_settings.chunk_overlap_size

    # ── Knowledge graph configuration ────────────────────────────────────

    async def get_kg_chunk_token_size(self) -> int:
        val = await self.get_setting("kg_chunk_token_size")
        return val if val is not None else 1200

    def get_kg_chunk_token_size_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_chunk_token_size")
        return val if val is not None else 1200

    async def get_kg_chunk_overlap_token_size(self) -> int:
        val = await self.get_setting("kg_chunk_overlap_token_size")
        return val if val is not None else 100

    def get_kg_chunk_overlap_token_size_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_chunk_overlap_token_size")
        return val if val is not None else 100

    async def get_kg_entity_extract_max_gleaning(self) -> int:
        val = await self.get_setting("kg_entity_extract_max_gleaning")
        return val if val is not None else 0

    def get_kg_entity_extract_max_gleaning_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_entity_extract_max_gleaning")
        return val if val is not None else 0

    async def get_kg_llm_model_max_async(self) -> int:
        val = await self.get_setting("kg_llm_model_max_async")
        return val if val is not None else 20

    def get_kg_llm_model_max_async_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_llm_model_max_async")
        return val if val is not None else 20

    async def get_kg_cosine_threshold(self) -> float:
        val = await self.get_setting("kg_cosine_threshold")
        return val if val is not None else 0.2

    def get_kg_cosine_threshold_sync(self) -> float:
        val = self.get_all_settings_sync().get("kg_cosine_threshold")
        return val if val is not None else 0.2

    async def get_kg_max_batch_size(self) -> int:
        val = await self.get_setting("kg_max_batch_size")
        return val if val is not None else 32

    def get_kg_max_batch_size_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_max_batch_size")
        return val if val is not None else 32

    async def get_kg_summary_max_tokens(self) -> int:
        val = await self.get_setting("kg_summary_max_tokens")
        return val if val is not None else 2000

    def get_kg_summary_max_tokens_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_summary_max_tokens")
        return val if val is not None else 2000

    async def get_kg_force_llm_summary_on_merge(self) -> int:
        val = await self.get_setting("kg_force_llm_summary_on_merge")
        return val if val is not None else 10

    def get_kg_force_llm_summary_on_merge_sync(self) -> int:
        val = self.get_all_settings_sync().get("kg_force_llm_summary_on_merge")
        return val if val is not None else 10

    async def get_kg_entity_types(self) -> list[str] | None:
        return await self.get_setting("kg_entity_types")

    def get_kg_entity_types_sync(self) -> list[str] | None:
        return self.get_all_settings_sync().get("kg_entity_types")

    async def get_max_graph_nodes(self) -> int:
        val = await self.get_setting("max_graph_nodes")
        return val if val is not None else 1000

    def get_max_graph_nodes_sync(self) -> int:
        val = self.get_all_settings_sync().get("max_graph_nodes")
        return val if val is not None else 1000

    # ── Cache configuration ──────────────────────────────────────────────

    async def get_cache_enabled(self) -> bool:
        val = await self.get_setting("cache_enabled")
        return val if val is not None else config_settings.cache_enabled

    def get_cache_enabled_sync(self) -> bool:
        val = self.get_all_settings_sync().get("cache_enabled")
        return val if val is not None else config_settings.cache_enabled

    async def get_cache_ttl(self) -> int:
        val = await self.get_setting("cache_ttl")
        return val if val is not None else config_settings.cache_ttl

    def get_cache_ttl_sync(self) -> int:
        val = self.get_all_settings_sync().get("cache_ttl")
        return val if val is not None else config_settings.cache_ttl

    # ── Parent-child chunking configuration ─────────────────────────────

    async def get_parent_child_enabled(self) -> bool:
        val = await self.get_setting("parent_child_enabled")
        return val if val is not None else False

    def get_parent_child_enabled_sync(self) -> bool:
        val = self.get_all_settings_sync().get("parent_child_enabled")
        return val if val is not None else False

    async def get_parent_chunk_size(self) -> int:
        val = await self.get_setting("parent_chunk_size")
        return val if val is not None else 800

    def get_parent_chunk_size_sync(self) -> int:
        val = self.get_all_settings_sync().get("parent_chunk_size")
        return val if val is not None else 800

    async def get_child_chunk_size(self) -> int:
        val = await self.get_setting("child_chunk_size")
        return val if val is not None else 150

    def get_child_chunk_size_sync(self) -> int:
        val = self.get_all_settings_sync().get("child_chunk_size")
        return val if val is not None else 150

    async def get_child_chunk_overlap(self) -> int:
        val = await self.get_setting("child_chunk_overlap")
        return val if val is not None else 50

    def get_child_chunk_overlap_sync(self) -> int:
        val = self.get_all_settings_sync().get("child_chunk_overlap")
        return val if val is not None else 50

    # ── Chunk separator configuration ──────────────────────────────────

    async def get_parent_chunk_separator(self) -> str:
        val = await self.get_setting("parent_chunk_separator")
        return val if val else ""

    def get_parent_chunk_separator_sync(self) -> str:
        val = self.get_all_settings_sync().get("parent_chunk_separator")
        return val if val else ""

    async def get_child_chunk_separator(self) -> str:
        val = await self.get_setting("child_chunk_separator")
        return val if val else ""

    def get_child_chunk_separator_sync(self) -> str:
        val = self.get_all_settings_sync().get("child_chunk_separator")
        return val if val else ""

    # ── Text preprocessing configuration ────────────────────────────────

    async def get_preprocess_collapse_whitespace(self) -> bool:
        val = await self.get_setting("preprocess_collapse_whitespace")
        return val if val is not None else False

    def get_preprocess_collapse_whitespace_sync(self) -> bool:
        val = self.get_all_settings_sync().get("preprocess_collapse_whitespace")
        return val if val is not None else False

    async def get_preprocess_remove_urls_emails(self) -> bool:
        val = await self.get_setting("preprocess_remove_urls_emails")
        return val if val is not None else False

    def get_preprocess_remove_urls_emails_sync(self) -> bool:
        val = self.get_all_settings_sync().get("preprocess_remove_urls_emails")
        return val if val is not None else False

    # ── Pause indexing ──────────────────────────────────────────────────

    async def get_pause_indexing(self) -> bool:
        val = await self.get_setting("pause_indexing")
        return bool(val) if val is not None else False

    def get_pause_indexing_sync(self) -> bool:
        val = self.get_all_settings_sync().get("pause_indexing")
        return bool(val) if val is not None else False

    async def set_pause_indexing(self, paused: bool):
        await self.update_setting("pause_indexing", paused)

    # ── Bulk operations ──────────────────────────────────────────────────

    async def get_all_settings(self) -> dict:
        settings = await self.db_ops.query_all_settings()
        return {s.key: json.loads(s.value) for s in settings}

    def get_all_settings_sync(self) -> dict:
        settings = db_ops.query_all_settings()
        return {s.key: json.loads(s.value) for s in settings}

    async def update_settings(self, settings: dict):
        for key, value in settings.items():
            if value is not None:
                await self.update_setting(key, value)

    async def test_mineru_token(self, token: str) -> dict:
        """Test the MinerU API token."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://mineru.net/api/v4/extract-results/batch/test-token",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return {"status_code": response.status_code, "data": response.json()}
            except httpx.RequestError as e:
                return {"status_code": 500, "data": {"msg": f"Request failed: {e}"}}


setting_service = SettingService()

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
from typing import List, Optional

from sqlalchemy import and_, select

from aperag.config import get_vector_db_connector
from aperag.db import models as db_models
from aperag.db.ops import async_db_ops
from aperag.exceptions import CollectionNotFoundException
from aperag.index.fulltext_index import create_index, fulltext_indexer
from aperag.index.manager import document_index_manager
from aperag.llm.embed.base_embedding import get_collection_embedding_service_sync
from aperag.service.document_service import _trigger_index_reconciliation
from aperag.utils.utils import (
    generate_fulltext_index_name,
    generate_vector_db_collection_name,
)

logger = logging.getLogger(__name__)

# List of all document index types that can be rebuilt by the repair flow.
REPAIRABLE_INDEX_TYPES = [
    db_models.DocumentIndexType.VECTOR,
    db_models.DocumentIndexType.FULLTEXT,
    db_models.DocumentIndexType.SUMMARY,
    db_models.DocumentIndexType.VISION,
]


class CollectionRepairService:
    """Scan a collection for inconsistent/missing index data and repair it.

    Problem context: the fulltext index path used to silently skip writing chunks
    when the Elasticsearch index did not exist, while still marking the index as
    ACTIVE. This service detects those broken states (missing ES index, ACTIVE
    fulltext index with zero chunks, missing vector collection, failed indexes)
    and, on request, repairs them by recreating the underlying stores and
    re-queuing the affected documents for re-indexing via the reconciler.
    """

    async def _scan_fulltext_index_state(self, collection_id: str) -> dict:
        """Return (index_exists, active_docs_without_chunks)."""
        index = generate_fulltext_index_name(collection_id)
        try:
            exists = fulltext_indexer.es.indices.exists(index=index).body
        except Exception as e:
            logger.warning(f"Failed to check fulltext index {index}: {e}")
            exists = False

        if not exists:
            return exists, []

        # Count chunks per document in one ES aggregation instead of one query per doc.
        try:
            resp = fulltext_indexer.es.search(
                index=index,
                body={"size": 0, "aggs": {"by_doc": {"terms": {"field": "document_id", "size": 10000}}}},
            )
            buckets = resp.get("aggregations", {}).get("by_doc", {}).get("buckets", [])
            chunk_counts = {b["key"]: b["doc_count"] for b in buckets}
        except Exception as e:
            logger.warning(f"Failed to aggregate chunks for index {index}: {e}")
            chunk_counts = {}

        # Fulltext-ACTIVE documents in this collection
        active_docs = await self._query_fulltext_active_docs(collection_id)
        missing = [doc_id for doc_id in active_docs if chunk_counts.get(doc_id, 0) == 0]
        return exists, missing

    async def _query_fulltext_active_docs(self, collection_id: str) -> List[str]:
        async def _query(session):
            stmt = (
                select(db_models.Document.id)
                .join(db_models.DocumentIndex, db_models.DocumentIndex.document_id == db_models.Document.id)
                .where(
                    and_(
                        db_models.Document.collection_id == collection_id,
                        db_models.Document.status != db_models.DocumentStatus.DELETED,
                        db_models.DocumentIndex.index_type == db_models.DocumentIndexType.FULLTEXT,
                        db_models.DocumentIndex.status == db_models.DocumentIndexStatus.ACTIVE,
                    )
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

        try:
            return await async_db_ops._execute_query(_query)
        except Exception as e:
            logger.error(f"Failed to query fulltext active docs for {collection_id}: {e}")
            return []

    async def _vector_collection_exists(self, collection_id: str) -> bool:
        try:
            name = generate_vector_db_collection_name(collection_id)
            conn = get_vector_db_connector(collection=name)
            return conn.connector.client.collection_exists(collection_name=name)
        except Exception as e:
            logger.warning(f"Failed to check vector collection for {collection_id}: {e}")
            return False

    async def scan(self, user_id: str, collection_id: str) -> dict:
        collection = await async_db_ops.query_collection(user_id, collection_id)
        if not collection:
            raise CollectionNotFoundException(collection_id)

        issues: List[dict] = []

        ft_exists, ft_missing_docs = await self._scan_fulltext_index_state(collection_id)
        if not ft_exists:
            issues.append(_issue(
                "fulltext_index_missing",
                "全文检索索引在 Elasticsearch 中不存在",
                "将重建全文索引，并对集合内文档重新排队执行全文索引。",
            ))
        elif ft_missing_docs:
            issues.append(_issue(
                "fulltext_docs_without_chunks",
                f"{len(ft_missing_docs)} 篇文档标记为已索引，但 Elasticsearch 中没有分块数据",
                "将把受影响文档的全文索引排队重建。",
                count=len(ft_missing_docs),
            ))

        if not await self._vector_collection_exists(collection_id):
            issues.append(_issue(
                "vector_collection_missing",
                "向量检索集合在向量数据库中不存在",
                "将重建向量集合，并对集合内文档重新排队执行向量索引。",
            ))

        failed = await async_db_ops.query_documents_with_failed_indexes(user_id, collection_id)
        if failed:
            issues.append(_issue(
                "failed_indexes",
                f"{len(failed)} 篇文档存在失败的索引",
                "将把失败的索引重新排队执行。",
                count=len(failed),
            ))

        return {"collection_id": collection_id, "healthy": len(issues) == 0, "issues": issues}

    async def repair(self, user_id: str, collection_id: str, codes: Optional[List[str]] = None) -> dict:
        collection = await async_db_ops.query_collection(user_id, collection_id)
        if not collection:
            raise CollectionNotFoundException(collection_id)

        # If no codes given, attempt everything the scanner reports as fixable.
        if not codes:
            scan_result = await self.scan(user_id, collection_id)
            codes = [i["code"] for i in scan_result["issues"] if i.get("fixable", True)]
            if not codes:
                return {"repaired": [], "message": "未检测到需修复的问题"}

        repaired: List[str] = []

        if "fulltext_index_missing" in codes:
            index = generate_fulltext_index_name(collection_id)
            create_index(index)  # idempotent: only creates if missing
            # Right after creation the index is empty, so rebuild all documents' fulltext.
            await self._mark_all_indexes_pending(user_id, collection_id, [db_models.DocumentIndexType.FULLTEXT])
            repaired.append("fulltext_index_missing")
            logger.info(f"Repaired fulltext index for collection {collection_id}")

        if "fulltext_docs_without_chunks" in codes:
            _, missing_docs = await self._scan_fulltext_index_state(collection_id)
            if missing_docs:
                await self._mark_pending_docs(missing_docs, db_models.DocumentIndexType.FULLTEXT)
                repaired.append("fulltext_docs_without_chunks")
                logger.info(f"Queued {len(missing_docs)} fulltext rebuilds for collection {collection_id}")

        if "vector_collection_missing" in codes:
            _, vector_size = get_collection_embedding_service_sync(collection)
            name = generate_vector_db_collection_name(collection_id)
            conn = get_vector_db_connector(collection=name)
            conn.connector.create_collection(vector_size=vector_size)
            await self._mark_all_indexes_pending(user_id, collection_id, [db_models.DocumentIndexType.VECTOR])
            repaired.append("vector_collection_missing")
            logger.info(f"Repaired vector collection for collection {collection_id}")

        if "failed_indexes" in codes:
            failed = await async_db_ops.query_documents_with_failed_indexes(user_id, collection_id)
            for doc_id, index_types in failed:
                await self._mark_pending_docs([doc_id], index_types)
            repaired.append("failed_indexes")
            logger.info(f"Queued failed index rebuilds for {len(failed)} docs in collection {collection_id}")

        if repaired:
            _trigger_index_reconciliation()

        return {"repaired": repaired, "message": f"已修复并重新排队：{', '.join(repaired)}"}

    async def _mark_all_indexes_pending(
        self, user_id: str, collection_id: str, index_types: List[db_models.DocumentIndexType]
    ) -> None:
        async def _txn(session):
            stmt = (
                select(db_models.Document.id)
                .where(
                    and_(
                        db_models.Document.user == user_id,
                        db_models.Document.collection_id == collection_id,
                        db_models.Document.status != db_models.DocumentStatus.DELETED,
                    )
                )
            )
            result = await session.execute(stmt)
            doc_ids = list(result.scalars().all())
            for doc_id in doc_ids:
                await document_index_manager.create_or_update_document_indexes(session, str(doc_id), index_types)

        await async_db_ops.execute_with_transaction(_txn)

    async def _mark_pending_docs(self, doc_ids: List[str], index_types: List[db_models.DocumentIndexType]) -> None:
        async def _txn(session):
            for doc_id in doc_ids:
                await document_index_manager.create_or_update_document_indexes(session, str(doc_id), index_types)

        await async_db_ops.execute_with_transaction(_txn)


def _issue(code: str, message: str, hint: str, count: Optional[int] = None) -> dict:
    issue = {"code": code, "level": "error", "fixable": True, "message": message, "hint": hint}
    if count is not None:
        issue["count"] = count
    return issue


collection_repair_service = CollectionRepairService()
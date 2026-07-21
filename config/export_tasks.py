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

import concurrent.futures
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import timedelta

from config.celery import app

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64 KB
MAX_DOWNLOAD_WORKERS = 5


@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def export_collection_task(self, export_task_id: str):
    """Celery task: package all object-store files under a collection prefix into a ZIP."""
    from sqlalchemy import select

    from aperag.config import get_sync_session
    from aperag.db.models import Collection, Document, ExportTask, ExportTaskStatus
    from aperag.objectstore.base import get_object_store
    from aperag.utils.utils import utc_now

    store = get_object_store()

    def _update_task(status=None, progress=None, message=None, error_message=None,
                     object_store_path=None, file_size=None):
        for session in get_sync_session():
            result = session.execute(select(ExportTask).where(ExportTask.id == export_task_id))
            task = result.scalars().first()
            if not task:
                return
            if status is not None:
                task.status = status
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if error_message is not None:
                task.error_message = error_message
            if object_store_path is not None:
                task.object_store_path = object_store_path
            if file_size is not None:
                task.file_size = file_size
            task.gmt_updated = utc_now()
            if status == ExportTaskStatus.COMPLETED:
                task.gmt_completed = utc_now()
                task.gmt_expires = utc_now() + timedelta(days=7)
            session.commit()

    temp_dir = None
    zip_path = None

    try:
        # Phase 1: read task info and move to PROCESSING
        user_id = None
        collection_id = None
        for session in get_sync_session():
            result = session.execute(select(ExportTask).where(ExportTask.id == export_task_id))
            task = result.scalars().first()
            if not task:
                logger.error(f"ExportTask {export_task_id} not found, aborting.")
                return
            user_id = task.user
            collection_id = task.collection_id
            task.status = ExportTaskStatus.PROCESSING
            task.progress = 0
            task.message = "Starting export..."
            task.gmt_updated = utc_now()
            session.commit()

        # Phase 2: list all files under the collection prefix
        prefix = f"user-{user_id}/{collection_id}/"
        object_paths = store.list_objects_by_prefix(prefix)
        total_files = len(object_paths)
        logger.info(f"ExportTask {export_task_id}: found {total_files} files under prefix '{prefix}'")

        _update_task(progress=5, message=f"Found {total_files} files. Starting download...")

        # Phase 3: create temp dir and download files concurrently
        temp_dir = tempfile.mkdtemp(prefix=f"export_{export_task_id}_")
        downloaded_count = [0]

        def _download_one(obj_path: str):
            rel_path = obj_path[len(prefix):]
            local_path = os.path.join(temp_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            stream = store.get(obj_path)
            if stream is None:
                logger.warning(f"Object not found at path: {obj_path}")
                return
            with open(local_path, "wb") as f:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            downloaded_count[0] += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
            executor.map(_download_one, object_paths)

        _update_task(
            progress=85,
            message=f"Downloaded {downloaded_count[0]} of {total_files} files. Generating manifest...",
        )

        # Phase 4: generate manifest.json from DB
        manifest = _build_manifest(collection_id, user_id, get_sync_session, Collection, Document)
        # Add full collection config for import reconstruction
        from aperag.schema.utils import parseCollectionConfig
        for session in get_sync_session():
            r = session.execute(select(Collection).where(Collection.id == collection_id))
            col = r.scalars().first()
            if col and col.config:
                try:
                    cc = parseCollectionConfig(col.config)
                    if cc.embedding and cc.embedding.model:
                        manifest["embedding_model"] = cc.embedding.model
                        manifest["embedding_provider"] = cc.embedding.model_service_provider or ""
                    # Include full config (entity_types, language, enable_*, etc.)
                    manifest["collection_config"] = json.loads(col.config)
                except Exception:
                    pass
        manifest_path = os.path.join(temp_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        _update_task(progress=90, message="Packaging ZIP...")

        # Phase 5: create ZIP archive
        zip_path = os.path.join(tempfile.gettempdir(), f"export_{export_task_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _dirs, files in os.walk(temp_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zf.write(file_path, arcname)

        _update_task(progress=95, message="Uploading ZIP to storage...")

        # Phase 6: upload ZIP to object store
        zip_object_path = f"exports/user-{user_id}/export_{export_task_id}.zip"
        with open(zip_path, "rb") as f:
            store.put(zip_object_path, f)

        file_size = os.path.getsize(zip_path)
        _update_task(
            status=ExportTaskStatus.COMPLETED,
            progress=100,
            message="Export complete.",
            object_store_path=zip_object_path,
            file_size=file_size,
        )
        logger.info(f"ExportTask {export_task_id} completed. ZIP size: {file_size} bytes")

    except Exception as exc:
        logger.exception(f"ExportTask {export_task_id} failed: {exc}")
        _update_task(status=ExportTaskStatus.FAILED, error_message=str(exc))

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and os.path.exists(zip_path):
            try:
                os.unlink(zip_path)
            except OSError:
                pass


def _build_manifest(collection_id: str, user_id: str, get_sync_session, Collection, Document) -> dict:
    from sqlalchemy import and_, select

    from aperag.db.models import CollectionStatus, DocumentStatus
    from aperag.utils.utils import utc_now

    collection_title = collection_id
    collection_description = ""
    documents = []

    for session in get_sync_session():
        col_result = session.execute(
            select(Collection).where(
                and_(Collection.id == collection_id, Collection.status != CollectionStatus.DELETED)
            )
        )
        collection = col_result.scalars().first()
        if collection:
            collection_title = collection.title or collection_id
            collection_description = collection.description or ""

        doc_result = session.execute(
            select(Document).where(
                and_(
                    Document.collection_id == collection_id,
                    Document.status == DocumentStatus.COMPLETE,
                )
            )
        )
        for doc in doc_result.scalars().all():
            documents.append(
                {
                    "id": doc.id,
                    "title": doc.name,
                    "status": doc.status if doc.status else "UNKNOWN",
                }
            )

    return {
        "schema_version": "1.0",
        "collection": {
            "id": collection_id,
            "title": collection_title,
            "description": collection_description,
            "exported_at": utc_now().isoformat(),
        },
        "documents": documents,
    }


# ── Full Export (Plan B): Qdrant + ES + PG ──────────────────────────────────

@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def export_collection_full_task(self, export_task_id: str):
    """Celery task: export Qdrant vectors + ES fulltext + PG graph data into a ZIP."""
    from sqlalchemy import select

    from aperag.config import get_sync_session
    from aperag.db.models import Collection, Document, ExportTask, ExportTaskStatus
    from aperag.objectstore.base import get_object_store
    from aperag.utils.utils import utc_now
    store = get_object_store()

    def _update_full(status=None, progress=None, message=None, error_message=None,
                     object_store_path=None, file_size=None):
        for session in get_sync_session():
            result = session.execute(select(ExportTask).where(ExportTask.id == export_task_id))
            t = result.scalars().first()
            if not t:
                return
            if status is not None:
                t.status = status
            if progress is not None:
                t.progress = progress
            if message is not None:
                t.message = message
            if error_message is not None:
                t.error_message = error_message
            if object_store_path is not None:
                t.object_store_path = object_store_path
            if file_size is not None:
                t.file_size = file_size
            t.gmt_updated = utc_now()
            if status == ExportTaskStatus.COMPLETED:
                t.gmt_completed = utc_now()
                t.gmt_expires = utc_now() + timedelta(days=7)
            session.commit()

    temp_dir = None
    zip_path = None

    try:
        user_id = None
        collection_id = None
        for session in get_sync_session():
            result = session.execute(select(ExportTask).where(ExportTask.id == export_task_id))
            task = result.scalars().first()
            if not task:
                return
            user_id = task.user
            collection_id = task.collection_id
            task.status = ExportTaskStatus.PROCESSING
            task.progress = 0
            task.message = "Full export: starting..."
            task.gmt_updated = utc_now()
            session.commit()

        workspace = collection_id

        _update_full(progress=5, message="Full export: connecting to storage...")

        temp_dir = tempfile.mkdtemp(prefix=f"export_full_{export_task_id}_")
        pg_dir = os.path.join(temp_dir, "pg")
        source_dir = os.path.join(temp_dir, "source")
        os.makedirs(pg_dir, exist_ok=True)
        os.makedirs(source_dir, exist_ok=True)

        # Phase 2: Qdrant
        _update_full(progress=10, message="Full export: dumping Qdrant vectors...")
        qdrant_points = _dump_qdrant(collection_id, os.path.join(temp_dir, "qdrant.jsonl"))

        # Phase 3: ES
        _update_full(progress=30, message="Full export: dumping Elasticsearch docs...")
        es_docs = _dump_es(collection_id, os.path.join(temp_dir, "es.jsonl"))

        # Phase 4: PG graph
        _update_full(progress=50, message="Full export: dumping PostgreSQL graph...")
        pg_counts = _dump_pg(workspace, pg_dir)

        # Phase 5: source files
        _update_full(progress=70, message="Full export: copying source files...")
        prefix = f"user-{user_id}/{collection_id}/"
        object_paths = store.list_objects_by_prefix(prefix)
        for obj_path in object_paths:
            rel_path = obj_path[len(prefix):]
            local_path = os.path.join(source_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            stream = store.get(obj_path)
            if stream is None:
                continue
            with open(local_path, "wb") as f:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)

        # Phase 6: manifest
        _update_full(progress=85, message="Full export: generating manifest...")
        manifest = _build_manifest(collection_id, user_id, get_sync_session, Collection, Document)
        manifest["export_type"] = "full"
        manifest["schema_version"] = "2.0"
        manifest["embedding_dim"] = _detect_embedding_dim(collection_id)
        from aperag.schema.utils import parseCollectionConfig
        for session in get_sync_session():
            r = session.execute(select(Collection).where(Collection.id == collection_id))
            col = r.scalars().first()
            if col and col.config:
                try:
                    cc = parseCollectionConfig(col.config)
                    if cc.embedding and cc.embedding.model:
                        manifest["embedding_model"] = cc.embedding.model
                        manifest["embedding_provider"] = cc.embedding.model_service_provider or ""
                    manifest["collection_config"] = json.loads(col.config)
                except Exception:
                    pass
        with open(os.path.join(temp_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # Phase 7: README
        emb_model = manifest.get("embedding_model", "unknown")
        emb_prov = manifest.get("embedding_provider", "unknown")
        emb_dim = manifest.get("embedding_dim", 0)
        with open(os.path.join(temp_dir, "README.txt"), "w", encoding="utf-8") as f:
            f.write("ApeRAG Full Export\n==================\n\n")
            f.write(f"Collection: {manifest['collection']['title']}\n")
            f.write(f"Exported: {manifest['collection']['exported_at']}\n\n")
            f.write(f"Embedding Model: {emb_model}\n")
            f.write(f"Embedding Provider: {emb_prov}\n")
            f.write(f"Embedding Dimension: {emb_dim}\n\n")
            f.write("Contents:\n")
            f.write(f"  qdrant.jsonl: {qdrant_points} vectors\n")
            f.write(f"  es.jsonl: {es_docs} fulltext docs\n")
            f.write(f"  pg/: {sum(pg_counts.values())} graph records\n")
            f.write("  source/: original files\n\n")
            f.write("IMPORTANT: The target ApeRAG instance must use the same embedding model.\n")
            f.write(f"  Model: {emb_model}\n")
            f.write(f"  Provider: {emb_prov}\n")

        # Phase 8: ZIP
        _update_full(progress=90, message="Full export: packaging ZIP...")
        zip_path = os.path.join(tempfile.gettempdir(), f"export_full_{export_task_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _dirs, files in os.walk(temp_dir):
                for filename in files:
                    fp = os.path.join(root, filename)
                    zf.write(fp, os.path.relpath(fp, temp_dir))

        # Phase 9: upload
        _update_full(progress=95, message="Full export: uploading ZIP...")
        zip_obj_path = f"exports/user-{user_id}/export_full_{export_task_id}.zip"
        with open(zip_path, "rb") as f:
            store.put(zip_obj_path, f)

        file_size = os.path.getsize(zip_path)
        _update_full(
            status=ExportTaskStatus.COMPLETED, progress=100,
            message="Full export complete.",
            object_store_path=zip_obj_path, file_size=file_size,
        )

    except Exception as exc:
        logger.exception(f"Full export {export_task_id} failed: {exc}")
        _update_full(status=ExportTaskStatus.FAILED, error_message=str(exc))
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and os.path.exists(zip_path):
            try:
                os.unlink(zip_path)
            except OSError:
                pass


def _dump_qdrant(collection_name: str, output_path: str) -> int:
    """Scroll all Qdrant points to JSONL."""
    from aperag.config import settings

    if settings.vector_db_type != "qdrant":
        return 0
    import qdrant_client
    ctx = json.loads(settings.vector_db_context)
    client = qdrant_client.QdrantClient(
        url=ctx.get("url", "http://localhost"),
        port=ctx.get("port", 6333),
        timeout=ctx.get("timeout", 300),
    )
    count = 0
    offset = None
    with open(output_path, "w", encoding="utf-8") as f:
        while True:
            points, next_offset = client.scroll(
                collection_name=collection_name, limit=100, offset=offset,
                with_vectors=True, with_payload=True,
            )
            if not points:
                break
            for p in points:
                vec = p.vector
                if isinstance(vec, dict):
                    vec = vec.get("", vec)
                f.write(json.dumps({"id": p.id, "vector": vec, "payload": p.payload}, ensure_ascii=False) + "\n")
                count += 1
            offset = next_offset
            if offset is None:
                break
    return count


def _dump_es(index_name: str, output_path: str) -> int:
    """Scroll all ES documents to JSONL."""
    from elasticsearch import Elasticsearch

    from aperag.config import settings

    es = Elasticsearch(settings.es_host, request_timeout=settings.es_timeout, max_retries=settings.es_max_retries)
    if not es.indices.exists(index=index_name).body:
        return 0
    count = 0
    resp = es.search(index=index_name, scroll="2m", size=100, body={"query": {"match_all": {}}})
    scroll_id = resp.get("_scroll_id")
    hits = resp["hits"]["hits"]
    with open(output_path, "w", encoding="utf-8") as f:
        while hits:
            for h in hits:
                f.write(json.dumps(h["_source"], ensure_ascii=False) + "\n")
                count += 1
            resp = es.scroll(scroll_id=scroll_id, scroll="2m")
            hits = resp["hits"]["hits"]
            scroll_id = resp.get("_scroll_id")
    es.clear_scroll(scroll_id=scroll_id)
    return count


def _dump_pg(workspace: str, output_dir: str) -> dict:
    """Export LightRAG PG tables to JSONL files."""
    from sqlalchemy import select

    from aperag.config import get_sync_session
    from aperag.db.models import (
        DocumentIndex,
        LightRAGDocChunksModel,
        LightRAGGraphEdge,
        LightRAGGraphNode,
        LightRAGVDBEntityModel,
        LightRAGVDBRelationModel,
    )

    configs = [
        ("graph_nodes.jsonl", LightRAGGraphNode,
         ["id","entity_id","entity_name","entity_type","description","source_id","file_path","workspace"]),
        ("graph_edges.jsonl", LightRAGGraphEdge,
         ["id","source_entity_id","target_entity_id","weight","keywords","description","source_id","file_path","workspace"]),
        ("vdb_entity.jsonl", LightRAGVDBEntityModel,
         ["id","entity_name","content","chunk_ids","file_path","workspace"]),
        ("vdb_relation.jsonl", LightRAGVDBRelationModel,
         ["id","source_id","target_id","content","chunk_ids","file_path","workspace"]),
        ("doc_chunks.jsonl", LightRAGDocChunksModel,
         ["id","full_doc_id","chunk_order_index","tokens","content","file_path","workspace"]),
        ("document_index.jsonl", DocumentIndex,
         ["id","document_id","index_type","status","version","observed_version","index_data","error_message"]),
    ]
    counts = {}
    for filename, model, cols in configs:
        fp = os.path.join(output_dir, filename)
        cnt = 0
        with open(fp, "w", encoding="utf-8") as f:
            for session in get_sync_session():
                stmt = select(*[getattr(model, c) for c in cols])
                if hasattr(model, "workspace"):
                    stmt = stmt.where(model.workspace == workspace)
                for row in session.execute(stmt).all():
                    rec = dict(zip(cols, row))
                    for k, v in rec.items():
                        if hasattr(v, "tolist"):
                            rec[k] = v.tolist()
                    f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                    cnt += 1
        counts[filename] = cnt
    return counts


def _detect_embedding_dim(collection_name: str) -> int:
    """Detect embedding dimension from Qdrant collection."""
    try:
        import qdrant_client as qc

        from aperag.config import settings
        ctx = json.loads(settings.vector_db_context)
        c = qc.QdrantClient(url=ctx.get("url","http://localhost"), port=ctx.get("port",6333), timeout=5)
        return c.get_collection(collection_name).config.params.vectors.size
    except Exception:
        return 0

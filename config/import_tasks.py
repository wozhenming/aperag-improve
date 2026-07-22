"""Import tasks — separate module for reliable Celery auto-discovery."""

import json as _json
import os as _os
import shutil as _shutil
import tempfile as _tempfile
import uuid as _uuid
import zipfile as _zipfile

from celery.utils.log import get_task_logger
from sqlalchemy import select, update

from config.celery import app

logger = get_task_logger(__name__)


@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def import_collection_task(self, import_task_id, target_embedding_model="", target_embedding_provider="",
                           target_embedding_custom_provider="",
                           target_completion_model="", target_completion_provider="",
                           target_completion_custom_provider="", export_type="basic"):
    """Celery task: import a ZIP (basic or full export) and restore the knowledge base."""
    logger.info(f"Import task {import_task_id}: STARTING (type={export_type}, model={target_embedding_model})")

    from aperag.config import get_sync_session
    from aperag.db.models import (
        Collection,
        Document,
        DocumentIndex,
        DocumentIndexStatus,
        DocumentIndexType,
        ImportTask,
        ImportTaskStatus,
    )
    from aperag.objectstore.base import get_object_store
    from aperag.utils.utils import utc_now

    def _update(status=None, progress=None, message=None, error_message=None,
                collection_id=None, collection_title=None):
        for session in get_sync_session():
            r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
            t = r.scalars().first()
            if not t:
                logger.warning(f"ImportTask {import_task_id}: not found in DB")
                return
            if status is not None:
                t.status = status
            if progress is not None:
                t.progress = progress
            if message is not None:
                t.message = message
            if error_message is not None:
                t.error_message = error_message
            if collection_id is not None:
                t.collection_id = collection_id
            if collection_title is not None:
                t.collection_title = collection_title
            t.gmt_updated = utc_now()
            if status == ImportTaskStatus.COMPLETED:
                t.gmt_completed = utc_now()
            session.commit()

    temp_dir = None

    try:
        user_id = None
        zip_path = None
        collection_title = "Imported Collection"
        for session in get_sync_session():
            r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
            t = r.scalars().first()
            if not t:
                logger.error(f"ImportTask {import_task_id}: NOT FOUND in DB, aborting!")
                return
            user_id = t.user
            zip_path = t.zip_path
            collection_title = t.collection_title or collection_title
            t.status = ImportTaskStatus.PROCESSING
            t.progress = 0
            t.message = "Import: extracting ZIP..."
            t.gmt_updated = utc_now()
            session.commit()

        logger.info(f"Import task {import_task_id}: user={user_id}, zip={zip_path}")

        _update(progress=5, message="Import: extracting ZIP...")

        if not zip_path or not _os.path.exists(zip_path):
            _update(status=ImportTaskStatus.FAILED, error_message=f"ZIP file not found: {zip_path}")
            logger.error(f"Import task {import_task_id}: ZIP not found at {zip_path}")
            return

        # Extract ZIP
        temp_dir = _tempfile.mkdtemp(prefix=f"import_{import_task_id}_")
        with _zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)
        logger.info(f"Import task {import_task_id}: ZIP extracted to {temp_dir}")

        # Read manifest
        manifest_path = _os.path.join(temp_dir, "manifest.json")
        if not _os.path.exists(manifest_path):
            _update(status=ImportTaskStatus.FAILED, error_message="manifest.json not found in ZIP")
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = _json.load(f)

        detected_type = manifest.get("export_type", "basic")
        logger.info(f"Import task {import_task_id}: detected export_type={detected_type}")

        _update(progress=15, message=f"Import: detected {detected_type} export, creating collection...")

        # Build collection config — use exported config as base, override with target models
        exported_config = manifest.get("collection_config", {})
        config_dict = dict(exported_config) if exported_config else {}
        # Ensure essential fields
        config_dict.setdefault("source", "system")
        config_dict.setdefault("enable_vector", True)
        config_dict.setdefault("enable_fulltext", True)
        config_dict.setdefault("enable_knowledge_graph", True)
        config_dict.setdefault("enable_summary", False)
        config_dict.setdefault("enable_vision", False)
        config_dict.setdefault("language", "zh-CN")
        config_dict.setdefault("knowledge_graph_config", {
            "entity_types": [
                "organization", "person", "geo", "event",
                "product", "technology", "date", "category",
            ]
        })
        # Override models with user-selected target models
        if target_embedding_model:
            config_dict["embedding"] = {"model": target_embedding_model, "temperature": 0.1}
            if target_embedding_provider:
                config_dict["embedding"]["model_service_provider"] = target_embedding_provider
            if target_embedding_custom_provider:
                config_dict["embedding"]["custom_llm_provider"] = target_embedding_custom_provider
        if target_completion_model:
            config_dict["completion"] = {"model": target_completion_model, "temperature": 0.1}
            if target_completion_provider:
                config_dict["completion"]["model_service_provider"] = target_completion_provider
            if target_completion_custom_provider:
                config_dict["completion"]["custom_llm_provider"] = target_completion_custom_provider
        coll_config = _json.dumps(config_dict)
        new_coll_id = _create_coll(user_id, collection_title, get_sync_session, Collection, utc_now, coll_config)
        old_coll_id = manifest.get("collection", {}).get("id", "")

        logger.info(f"Import task {import_task_id}: created collection {new_coll_id}")

        _update(progress=25, message="Import: creating document records...", collection_id=new_coll_id)

        # Create document records & ID mapping
        doc_id_map = {}
        for doc_info in manifest.get("documents", []):
            old_doc_id = doc_info.get("id", "")
            doc_name = doc_info.get("title", old_doc_id)
            new_doc_id = _create_doc(new_coll_id, user_id, doc_name, get_sync_session, Document, utc_now)
            doc_id_map[old_doc_id] = new_doc_id

        logger.info(f"Import task {import_task_id}: created {len(doc_id_map)} documents")

        # Copy source files to object store and set document object_path
        _update(progress=35, message="Import: copying source files...")
        store = get_object_store()
        file_count = 0
        # Source files may be at root (basic export) or under source/ (full export)
        for search_root in [temp_dir, _os.path.join(temp_dir, "source")]:
            if not _os.path.exists(search_root):
                continue
            for root, _dirs, files in _os.walk(search_root):
                for filename in files:
                    if filename in ("manifest.json", "README.txt"):
                        continue
                    fp = _os.path.join(root, filename)
                    rel = _os.path.relpath(fp, search_root)
                    # rel is like "{old_doc_id}/parsed.md"
                    parts = rel.split("/", 1)
                    old_doc = parts[0]
                    subpath = parts[1] if len(parts) > 1 else filename
                    if old_doc in doc_id_map:
                        new_doc = doc_id_map[old_doc]
                        obj_path = f"user-{user_id}/{new_coll_id}/{new_doc}/{subpath}"
                        _update_doc_object_path(new_doc, obj_path, get_sync_session, Document)
                        with open(fp, "rb") as sf:
                            store.put(obj_path, sf)
                        # Update document size from the actual file
                        file_sz = _os.path.getsize(fp)
                        _update_doc_size(new_doc, file_sz, get_sync_session, Document)
                        file_count += 1
        logger.info(f"Import task {import_task_id}: copied {file_count} source files")

        _update(progress=45, message="Import: creating index records...")
        _create_indexes(doc_id_map, get_sync_session, DocumentIndex, DocumentIndexType, DocumentIndexStatus)

        if detected_type == "full":
            ok = _check_embedding_match(manifest)
            if not ok:
                logger.warning(f"Import task {import_task_id}: embedding mismatch, pausing")
                exp_model = manifest.get("embedding_model", "?")
                exp_dim = manifest.get("embedding_dim", "?")
                _update(
                    status="INCOMPATIBLE", progress=55,
                    message=f"Embedding model mismatch. Export: {exp_model} (dim={exp_dim}). Choose: re-index or cancel.",
                )
                return

            _update(progress=55, message="Import: restoring Qdrant vectors...")
            qf = _os.path.join(temp_dir, "qdrant.jsonl")
            if _os.path.exists(qf):
                _restore_qdrant(qf, new_coll_id)

            _update(progress=70, message="Import: restoring Elasticsearch documents...")
            ef = _os.path.join(temp_dir, "es.jsonl")
            if _os.path.exists(ef):
                _restore_es(ef, new_coll_id, doc_id_map)

            _update(progress=85, message="Import: restoring PostgreSQL graph data...")
            pg_dir = _os.path.join(temp_dir, "pg")
            if _os.path.exists(pg_dir):
                _restore_pg(pg_dir, new_coll_id, old_coll_id)
        else:
            _update(progress=55, message="Import: triggering re-index...")
            _trigger_reindex(doc_id_map, get_sync_session)

        _update(
            status=ImportTaskStatus.COMPLETED, progress=100,
            message="Import complete.", collection_id=new_coll_id,
            collection_title=collection_title,
        )
        logger.info(f"Import task {import_task_id}: COMPLETED, collection={new_coll_id}")

        # Trigger immediate index reconciliation for the new collection
        from config.celery_tasks import reconcile_indexes_task
        reconcile_indexes_task.delay()

    except Exception as exc:
        logger.exception(f"Import task {import_task_id}: FAILED with exception: {exc}")
        _update(status=ImportTaskStatus.FAILED, error_message=str(exc))
    finally:
        if temp_dir and _os.path.exists(temp_dir):
            _shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and _os.path.exists(zip_path):
            try:
                _os.unlink(zip_path)
            except OSError:
                pass


@app.task(bind=True, soft_time_limit=55 * 60, time_limit=60 * 60)
def import_collection_reindex_task(self, import_task_id):
    """Celery task: continue a paused import by triggering re-index."""
    logger.info(f"Reindex task {import_task_id}: STARTING")

    from aperag.config import get_sync_session
    from aperag.db.models import Document, DocumentIndex, DocumentIndexStatus, ImportTask, ImportTaskStatus
    from aperag.utils.utils import utc_now

    for session in get_sync_session():
        r = session.execute(select(ImportTask).where(ImportTask.id == import_task_id))
        t = r.scalars().first()
        if not t:
            logger.error(f"Reindex task {import_task_id}: ImportTask not found")
            return
        collection_id = t.collection_id
        t.status = ImportTaskStatus.PROCESSING
        t.progress = 55
        t.message = "Import: re-indexing with target model..."
        t.gmt_updated = utc_now()
        session.commit()

        doc_stmt = select(Document.id).where(Document.collection_id == collection_id)
        doc_ids = [r[0] for r in session.execute(doc_stmt).all()]
        logger.info(f"Reindex task {import_task_id}: found {len(doc_ids)} docs to re-index")

        for did in doc_ids:
            session.execute(
                update(DocumentIndex)
                .where(DocumentIndex.document_id == did)
                .values(status=DocumentIndexStatus.PENDING, version=DocumentIndex.version + 1)
            )
            # Also update document status to PENDING so reconciler picks it up
            session.execute(
                update(Document)
                .where(Document.id == did)
                .values(status="PENDING")
            )

        t.status = ImportTaskStatus.COMPLETED
        t.progress = 100
        t.message = "Import complete (re-indexed with target model)."
        t.gmt_completed = utc_now()
        session.commit()
        logger.info(f"Reindex task {import_task_id}: COMPLETED")


# ── Helper functions ─────────────────────────────────────────────────

def _create_coll(user_id, title, get_sync_session, Collection, utc_now, config="{}"):
    from aperag.db.models import CollectionStatus

    cid = f"col{_uuid.uuid4().hex[:16]}"
    for s in get_sync_session():
        s.add(Collection(id=cid, user=user_id, title=title, type="document",
                          status=CollectionStatus.ACTIVE, config=config))
        s.commit()
    return cid


def _create_doc(collection_id, user_id, name, get_sync_session, Document, utc_now):
    from aperag.db.models import DocumentStatus

    did = f"doc{_uuid.uuid4().hex[:16]}"
    for s in get_sync_session():
        s.add(Document(id=did, collection_id=collection_id, user=user_id, name=name,
                        status=DocumentStatus.PENDING, size=0, doc_metadata="{}", object_path=""))
        s.commit()
    return did


def _update_doc_size(doc_id, size, get_sync_session, Document):
    from sqlalchemy import update as sql_update

    for s in get_sync_session():
        s.execute(sql_update(Document).where(Document.id == doc_id).values(size=size))
        s.commit()


def _update_doc_object_path(doc_id, object_path, get_sync_session, Document):
    """Set the object_path on a document so reconciler can find its files."""
    from sqlalchemy import update as sql_update

    for s in get_sync_session():
        s.execute(sql_update(Document).where(Document.id == doc_id).values(object_path=object_path))
        s.commit()


def _create_indexes(doc_id_map, get_sync_session, DocumentIndex, DocumentIndexType, DocumentIndexStatus):
    all_types = [DocumentIndexType.VECTOR, DocumentIndexType.FULLTEXT, DocumentIndexType.GRAPH]
    for s in get_sync_session():
        for ndid in doc_id_map.values():
            for it in all_types:
                s.add(DocumentIndex(document_id=ndid, index_type=it,
                                     status=DocumentIndexStatus.PENDING, version=1, observed_version=0))
        s.commit()


def _trigger_reindex(doc_id_map, get_sync_session):
    from aperag.db.models import Document, DocumentIndex, DocumentIndexStatus

    for s in get_sync_session():
        for ndid in doc_id_map.values():
            s.execute(
                update(DocumentIndex)
                .where(DocumentIndex.document_id == ndid)
                .values(status=DocumentIndexStatus.PENDING, version=DocumentIndex.version + 1)
            )
            s.execute(
                update(Document)
                .where(Document.id == ndid)
                .values(status="PENDING")
            )
        s.commit()


def _check_embedding_match(manifest):
    export_dim = manifest.get("embedding_dim", 0)
    if not export_dim:
        return True

    try:
        import qdrant_client as qc

        from aperag.config import settings

        ctx = _json.loads(settings.vector_db_context)
        client = qc.QdrantClient(
            url=ctx.get("url", "http://localhost"),
            port=ctx.get("port", 6333), timeout=5,
        )
        for c in client.get_collections().collections:
            try:
                info = client.get_collection(c.name)
                if info.config.params.vectors.size == export_dim:
                    return True
            except Exception:
                pass
        logger.warning(f"Embedding dim mismatch: export={export_dim}, no matching collection found")
        return False
    except Exception as e:
        logger.warning(f"Could not verify embedding compatibility: {e}, assuming compatible")
        return True


def _restore_qdrant(jsonl_path, collection_name):
    from aperag.config import settings

    if settings.vector_db_type != "qdrant":
        return
    import qdrant_client
    from qdrant_client.models import Distance, VectorParams

    ctx = _json.loads(settings.vector_db_context)
    client = qdrant_client.QdrantClient(
        url=ctx.get("url", "http://localhost"),
        port=ctx.get("port", 6333), timeout=300,
    )
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    with open(jsonl_path, "r", encoding="utf-8") as f:
        dim = len(_json.loads(f.readline()).get("vector", []))
    client.create_collection(collection_name, VectorParams(size=dim, distance=Distance.COSINE))
    points = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = _json.loads(line)
            points.append(qdrant_client.models.PointStruct(
                id=rec["id"], vector=rec["vector"], payload=rec.get("payload", {})))
            if len(points) >= 100:
                client.upsert(collection_name=collection_name, points=points)
                points = []
    if points:
        client.upsert(collection_name=collection_name, points=points)
    logger.info(f"Restored {len(points)} Qdrant points to {collection_name}")


def _restore_es(jsonl_path, collection_id, doc_id_map):
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk

    from aperag.config import settings

    es = Elasticsearch(settings.es_host, request_timeout=settings.es_timeout, max_retries=settings.es_max_retries)
    index_name = str(collection_id)
    if not es.indices.exists(index=index_name).body:
        from aperag.index.fulltext_index import create_index as _create_es_idx

        _create_es_idx(index_name)
    actions = []
    count = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            doc = _json.loads(line)
            oid = doc.get("document_id", "")
            if oid in doc_id_map:
                doc["document_id"] = doc_id_map[oid]
            actions.append({"_index": index_name, "_source": doc})
            count += 1
            if len(actions) >= 100:
                bulk(es, actions)
                actions = []
    if actions:
        bulk(es, actions)
    logger.info(f"Restored {count} ES documents to {index_name}")


def _restore_pg(pg_dir, new_ws, old_ws):
    from aperag.config import get_sync_session
    from aperag.db.models import (
        LightRAGDocChunksModel,
        LightRAGGraphEdge,
        LightRAGGraphNode,
        LightRAGVDBEntityModel,
        LightRAGVDBRelationModel,
    )

    # Skip auto-increment `id` columns — let the database assign new IDs
    tmap = {
        "graph_nodes.jsonl": (LightRAGGraphNode,
                               ["entity_id","entity_name","entity_type","description","source_id","file_path","workspace"]),
        "graph_edges.jsonl": (LightRAGGraphEdge,
                               ["source_entity_id","target_entity_id","weight","keywords","description","source_id","file_path","workspace"]),
        "vdb_entity.jsonl": (LightRAGVDBEntityModel,
                              ["id","entity_name","content","chunk_ids","file_path","workspace"]),
        "vdb_relation.jsonl": (LightRAGVDBRelationModel,
                                ["id","source_id","target_id","content","chunk_ids","file_path","workspace"]),
        "doc_chunks.jsonl": (LightRAGDocChunksModel,
                              ["id","full_doc_id","chunk_order_index","tokens","content","file_path","workspace"]),
    }

    total = 0
    for fn, (model, cols) in tmap.items():
        fp = _os.path.join(pg_dir, fn)
        if not _os.path.exists(fp):
            continue
        rows = []
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                rec = _json.loads(line)
                rec["workspace"] = new_ws
                for k in ("id","entity_id","source_id","target_id","source_entity_id","target_entity_id"):
                    if k in rec and isinstance(rec[k], str) and old_ws:
                        rec[k] = rec[k].replace(f":{old_ws}", f":{new_ws}")
                rows.append(rec)
        for s in get_sync_session():
            for row in rows:
                s.add(model(**{k: row.get(k) for k in cols}))
            s.commit()
        total += len(rows)
    logger.info(f"Restored {total} PG graph records to workspace={new_ws}")

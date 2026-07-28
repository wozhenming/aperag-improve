import json
import logging
import os
from typing import Any, Dict

import qdrant_client
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client.http.models import ScoredPoint
from qdrant_client.models import VectorParams

from aperag.query.query import DocumentWithScore, QueryResult, QueryWithEmbedding
from aperag.vectorstore.base import VectorStoreConnector

logger = logging.getLogger(__name__)


class QdrantVectorStoreConnector(VectorStoreConnector):
    def __init__(self, ctx: Dict[str, Any], **kwargs: Any) -> None:
        super().__init__(ctx, **kwargs)
        self.ctx = ctx
        self.collection_name = ctx.get("collection", "collection")

        self.url = ctx.get("url", "http://localhost")
        self.port = ctx.get("port", 6333)
        self.grpc_port = ctx.get("grpc_port", 6334)
        self.prefer_grpc = ctx.get("prefer_grpc", False)
        self.https = ctx.get("https", False)
        self.timeout = ctx.get("timeout", 300)
        self.vector_size = ctx.get("vector_size", 1536)
        self.distance = ctx.get("distance", "Cosine")

        if self.url == ":memory:":
            self.client = qdrant_client.QdrantClient(":memory:")
        else:
            self.client = qdrant_client.QdrantClient(
                url=self.url,
                port=self.port,
                grpc_port=self.grpc_port,
                prefer_grpc=self.prefer_grpc,
                https=self.https,
                timeout=self.timeout,
                **kwargs,
            )

        self.store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=self.distance),
        )

    def search(self, query: QueryWithEmbedding, **kwargs):
        consistency = kwargs.get("consistency", "majority")
        search_params = kwargs.get("search_params")
        score_threshold = kwargs.get("score_threshold", 0.1)
        filter_conditions = kwargs.get("filter")

        hits = self.client.query_points(
            collection_name=self.collection_name,
            query=query.embedding,
            with_vectors=True,
            limit=query.top_k,
            consistency=consistency,
            search_params=search_params,
            score_threshold=score_threshold,
            query_filter=filter_conditions,
        )

        results = [self._convert_scored_point_to_document_with_score(point) for point in hits.points]
        results = [result for result in results if result is not None]

        return QueryResult(
            query=query.query,
            results=results,
        )

    def _convert_scored_point_to_document_with_score(self, scored_point: ScoredPoint) -> DocumentWithScore | None:
        try:
            payload = scored_point.payload or {}
            text = scored_point.payload.get("text") or json.loads(payload["_node_content"]).get("text")
            metadata = payload.get("metadata") or json.loads(payload["_node_content"]).get("metadata")
            # Try relationships fallback if source is missing or empty (covers old index data)
            if not metadata.get("source"):
                try:
                    relationships = json.loads(payload["_node_content"]).get("relationships")
                    if relationships and relationships.get("1"):
                        source = relationships["1"].get("metadata", {}).get("source")
                        if source:
                            metadata["source"] = os.path.basename(source)
                except Exception:
                    pass  # safe fallback, don't drop the result

            # When parent-child chunking is active, return the full parent content
            # for richer LLM context instead of the matched child chunk
            if metadata and metadata.get("parent_content"):
                text = metadata["parent_content"]

            return DocumentWithScore(
                id=scored_point.id,
                text=text,  # type: ignore
                metadata=metadata,  # type: ignore
                embedding=scored_point.vector,  # type: ignore
                score=scored_point.score,
            )
        except Exception:
            logger.exception("Failed to convert scored point to document")
            return None

    def delete(self, **delete_kwargs: Any):
        ids = delete_kwargs.get("ids")
        if ids:
            self.store.delete_nodes(ids)

    def create_collection(self, **kwargs: Any):
        vector_size = kwargs.get("vector_size")
        from qdrant_client.http import models as rest

        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=rest.VectorParams(
                size=vector_size,
                distance=rest.Distance.COSINE,
            ),
        )

    def delete_collection(self, **kwargs: Any):
        self.client.delete_collection(collection_name=self.collection_name)

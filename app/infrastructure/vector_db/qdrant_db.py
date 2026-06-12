"""QdrantDB: adaptador VectorDBInterface per a Qdrant self-hosted.

Backend pensat per al CORPUS COMPLET (~575k chunks) al propi VPS, gratis i
sense els límits del free tier de cap proveïdor:
  - Quantització escalar INT8 (4x) + vectors `on_disk` -> els vectors quantitzats
    caben en poca RAM i els originals viuen al disc (128 GB de sobres).
  - Com Pinecone: el TEXT viu al ChunkStore (SQLite); Qdrant només guarda
    (id, vector, payload mínim amb chunk_id + author per al filtre).
  - Vectors normalitzats per l'embedder -> distància cosine.

Qdrant no admet IDs string arbitraris, així que el chunk_id ("fitxer.txt#3") es
converteix a un UUID determinista; el chunk_id real va al payload per hidratar.
"""
from __future__ import annotations
import uuid
from typing import Sequence

from app.domain.models import Chunk, RetrievedChunk
from app.infrastructure.chunk_store import ChunkStore

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "sigphi.qdrant")


class QdrantDB:
    def __init__(
        self,
        url: str,
        collection: str,
        chunk_store: ChunkStore,
        use_quantization: bool = True,
    ) -> None:
        from qdrant_client import QdrantClient

        self._local = url == ":memory:"
        self._client = (
            QdrantClient(location=":memory:") if self._local else QdrantClient(url=url)
        )
        self._collection = collection
        self._chunk_store = chunk_store
        self._use_quantization = use_quantization

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, chunk_id))

    def initialize_index(self, dim: int) -> None:
        from qdrant_client import models

        if self._client.collection_exists(self._collection):
            return

        quant = None
        if self._use_quantization and not self._local:
            quant = models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    always_ram=True,
                )
            )
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
                on_disk=not self._local,
            ),
            quantization_config=quant,
        )

    def upsert_batches(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[list[float]],
        batch_size: int = 100,
    ) -> int:
        from qdrant_client import models

        if len(chunks) != len(vectors):
            raise ValueError("chunks i vectors han de tenir la mateixa llargada")
        if not chunks:
            return 0

        # Text + metadata completa al ChunkStore (resumible)
        self._chunk_store.upsert_many(chunks)

        total = 0
        for start in range(0, len(chunks), batch_size):
            bc = chunks[start : start + batch_size]
            bv = vectors[start : start + batch_size]
            points = [
                models.PointStruct(
                    id=self._point_id(c.chunk_id),
                    vector=list(v),
                    payload={"chunk_id": c.chunk_id, "author": c.author},
                )
                for c, v in zip(bc, bv)
            ]
            self._client.upsert(collection_name=self._collection, points=points)
            total += len(points)
        return total

    def query_similarity(
        self,
        vector: list[float],
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        from qdrant_client import models

        qfilter = None
        if author_filter:
            qfilter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="author", match=models.MatchAny(any=author_filter)
                    )
                ]
            )
        res = self._client.query_points(
            collection_name=self._collection,
            query=list(vector),
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        ).points

        ids = [(p.payload or {}).get("chunk_id") for p in res]
        hydrated = self._chunk_store.get_by_ids([c for c in ids if c])

        out: list[RetrievedChunk] = []
        for p in res:
            cid = (p.payload or {}).get("chunk_id")
            chunk = hydrated.get(cid)
            if chunk is None:
                continue
            out.append(RetrievedChunk(chunk=chunk, score=float(p.score)))
        return out

    def delete_chunk_ids(self, chunk_ids: list[str]) -> int:
        """Esborra de Qdrant els punts d'aquests chunk_id (neteja, sense re-embed)."""
        if not chunk_ids:
            return 0
        ids = [self._point_id(c) for c in chunk_ids]
        self._client.delete(collection_name=self._collection, points_selector=ids)
        return len(ids)

"""PineconeDB: adaptador VectorDBInterface per a Pinecone (backend ACTIU).

Disseny pensat per al free tier (Starter) amb 575k+ fragments i només 4 GB de
RAM al VPS:
  - Pinecone guarda NOMES (id, vector, metadata curta): author / work / language
    / completeness / authorship / note. El TEXT complet NO hi va (límit de
    metadata del free tier).
  - El text viu al ChunkStore (SQLite local). query_similarity hidrata el text
    des del ChunkStore abans de retornar RetrievedChunk complets.
  - L'embedder normalitza els vectors (normalize=True) -> metric "cosine".
"""
from __future__ import annotations
from typing import Sequence

from app.domain.models import Chunk, RetrievedChunk
from app.infrastructure.chunk_store import ChunkStore


class PineconeDB:
    """Vector store sobre Pinecone + ChunkStore (text) per al free tier."""

    def __init__(
        self,
        api_key: str,
        index_name: str,
        chunk_store: ChunkStore,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        if not api_key:
            raise ValueError(
                "PINECONE_API_KEY no està configurada. Defineix-la al .env "
                "abans d'usar el backend Pinecone."
            )
        from pinecone import Pinecone

        self._pc = Pinecone(api_key=api_key)
        self._index_name = index_name
        self._cloud = cloud
        self._region = region
        self._chunk_store = chunk_store
        self._index = None  # lazy

    def _get_index(self):
        if self._index is None:
            self._index = self._pc.Index(self._index_name)
        return self._index

    def initialize_index(self, dim: int) -> None:
        """Crea l'índex serverless si no existeix. Idempotent."""
        from pinecone import ServerlessSpec

        existing = [ix["name"] for ix in self._pc.list_indexes()]
        if self._index_name not in existing:
            self._pc.create_index(
                name=self._index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud=self._cloud, region=self._region),
            )
        self._index = self._pc.Index(self._index_name)

    @staticmethod
    def _metadata(c: Chunk) -> dict:
        """Metadata curta per a Pinecone (sense el text del chunk)."""
        return {
            "author": c.author,
            "work": c.work,
            "language": c.language,
            "completeness": c.completeness,
            "authorship": c.authorship,
            "note": c.note,
        }

    def upsert_batches(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[list[float]],
        batch_size: int = 100,
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks i vectors han de tenir la mateixa llargada")
        if not chunks:
            return 0

        # 1) Text + metadata al ChunkStore (resumible: INSERT OR REPLACE)
        self._chunk_store.upsert_many(chunks)

        # 2) Vectors + metadata curta a Pinecone, en lots
        index = self._get_index()
        total = 0
        for start in range(0, len(chunks), batch_size):
            bc = chunks[start : start + batch_size]
            bv = vectors[start : start + batch_size]
            items = [
                {"id": c.chunk_id, "values": list(v), "metadata": self._metadata(c)}
                for c, v in zip(bc, bv)
            ]
            index.upsert(vectors=items)
            total += len(items)
        return total

    def query_similarity(
        self,
        vector: list[float],
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        index = self._get_index()
        flt = {"author": {"$in": author_filter}} if author_filter else None
        res = index.query(
            vector=list(vector),
            top_k=top_k,
            include_metadata=True,
            filter=flt,
        )
        matches = res["matches"] if isinstance(res, dict) else res.matches

        def field(m, key):
            return m[key] if isinstance(m, dict) else getattr(m, key)

        ids = [field(m, "id") for m in matches]
        hydrated = self._chunk_store.get_by_ids(ids)

        out: list[RetrievedChunk] = []
        for m in matches:
            mid = field(m, "id")
            score = field(m, "score")
            chunk = hydrated.get(mid)
            if chunk is None:
                # Fallback si el ChunkStore i Pinecone es desincronitzen:
                # construeix des de la metadata (sense text).
                md = field(m, "metadata") or {}
                chunk = Chunk(
                    chunk_id=mid,
                    text="",
                    author=md.get("author", ""),
                    work=md.get("work", ""),
                    language=md.get("language", ""),
                    completeness=md.get("completeness", ""),
                    authorship=md.get("authorship", ""),
                    note=md.get("note", ""),
                )
            out.append(RetrievedChunk(chunk=chunk, score=float(score)))
        return out

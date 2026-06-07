"""ChromaDB: adaptador VectorDBInterface per a ChromaDB local (backend FUTUR).

Germana de PineconeDB amb el MATEIX contracte. S'activarà amb
VECTOR_DB_TYPE=chroma quan el VPS tingui prou RAM (>= 16 GB) per allotjar
l'índex de 575k fragments en local.

A diferència de Pinecone, Chroma desa el text com a `documents`, així que és
autocontingut i NO necessita ChunkStore.
"""
from __future__ import annotations
from pathlib import Path
from typing import Sequence

from app.domain.models import Chunk, RetrievedChunk

_COLLECTION = "sigphi"


class ChromaDB:
    """Vector store local sobre ChromaDB (persistent)."""

    def __init__(self, persist_dir: Path) -> None:
        import chromadb

        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = None  # lazy

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def initialize_index(self, dim: int) -> None:
        # Chroma crea la col·lecció sota demanda; la dimensió s'infereix
        # dels primers embeddings inserits.
        self._get_collection()

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
        col = self._get_collection()
        total = 0
        for start in range(0, len(chunks), batch_size):
            bc = chunks[start : start + batch_size]
            bv = vectors[start : start + batch_size]
            col.upsert(
                ids=[c.chunk_id for c in bc],
                embeddings=[list(v) for v in bv],
                documents=[c.text for c in bc],
                metadatas=[
                    {
                        "author": c.author,
                        "work": c.work,
                        "language": c.language,
                        "completeness": c.completeness,
                        "authorship": c.authorship,
                        "note": c.note,
                    }
                    for c in bc
                ],
            )
            total += len(bc)
        return total

    def query_similarity(
        self,
        vector: list[float],
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        col = self._get_collection()
        where = {"author": {"$in": author_filter}} if author_filter else None
        res = col.query(
            query_embeddings=[list(vector)],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]

        out: list[RetrievedChunk] = []
        for cid, doc, md, dist in zip(ids, docs, metas, dists):
            md = md or {}
            chunk = Chunk(
                chunk_id=cid,
                text=doc or "",
                author=md.get("author", ""),
                work=md.get("work", ""),
                language=md.get("language", ""),
                completeness=md.get("completeness", ""),
                authorship=md.get("authorship", ""),
                note=md.get("note", ""),
            )
            # cosine space: distance = 1 - similitud  ->  score = 1 - distance
            out.append(RetrievedChunk(chunk=chunk, score=1.0 - float(dist)))
        return out

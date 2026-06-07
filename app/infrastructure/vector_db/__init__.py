"""Factory del backend de vector DB.

build_vector_db(settings) tria la implementació segons settings.vector_db_type:
  - "pinecone": PineconeDB (actiu) + ChunkStore per al text.
  - "chroma":   ChromaDB (local, futur), autocontingut.

Els imports dels adaptadors són lazy (dins de cada branca) perquè no calgui
tenir instal·lat el client de Pinecone si fas servir Chroma, i viceversa.
"""
from __future__ import annotations

from app.config import Settings
from app.domain.interfaces import VectorDBInterface
from app.infrastructure.chunk_store import ChunkStore


def build_vector_db(
    settings: Settings,
    chunk_store: ChunkStore | None = None,
) -> VectorDBInterface:
    """Construeix el vector store actiu segons la configuració."""
    if settings.vector_db_type == "pinecone":
        from app.infrastructure.vector_db.pinecone_db import PineconeDB

        cs = chunk_store or ChunkStore(settings.chunk_store_path)
        return PineconeDB(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            chunk_store=cs,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        )

    if settings.vector_db_type == "chroma":
        from app.infrastructure.vector_db.chroma_db import ChromaDB

        return ChromaDB(persist_dir=settings.chroma_dir)

    if settings.vector_db_type == "qdrant":
        from app.infrastructure.vector_db.qdrant_db import QdrantDB

        cs = chunk_store or ChunkStore(settings.chunk_store_path)
        return QdrantDB(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            chunk_store=cs,
            use_quantization=settings.qdrant_use_quantization,
        )

    raise ValueError(f"vector_db_type desconegut: {settings.vector_db_type!r}")

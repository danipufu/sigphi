"""Interfícies del domini. Implementades per adaptadors a infrastructure/."""
from __future__ import annotations
from typing import Protocol, Sequence

from app.domain.models import Chunk, RetrievedChunk


class VectorDBInterface(Protocol):
    """Contracte que qualsevol vector store ha d'implementar
    (Pinecone, ChromaDB local, futurs proveïdors).
    """

    def initialize_index(self, dim: int) -> None:
        """Crea l'índex si no existeix. Idempotent: si ja existeix, no fa res."""
        ...

    def upsert_batches(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[list[float]],
        batch_size: int = 100,
    ) -> int:
        """Puja (chunk, vector) en lots de mida batch_size.

        Optimitzat per a càrregues massives (575k+ fragments) de forma resumible:
        - chunks i vectors han de tenir la mateixa llargada.
        - Retorna el nombre total de fragments pujats amb èxit.
        - El text complet del chunk es desa per separat al ChunkStore (SQLite),
          NO a la metadata del vector store (per cabre al Pinecone free tier).
        """
        ...

    def query_similarity(
        self,
        vector: list[float],
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Cerca semàntica top-k.

        author_filter ve de la detecció d'autor en 12 idiomes (RetrievalService).
        Si es proporciona, restringeix la cerca als chunks d'aquells autors.
        Si None, cerca a tot l'índex.
        """
        ...


class EmbedderInterface(Protocol):
    """Contracte del model d'embeddings (sentence-transformers multilingüe)."""

    @property
    def dimension(self) -> int:
        """Mida del vector que produeix (384 per a paraphrase-multilingual-MiniLM-L12-v2)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Vectoritza UNA consulta (optimitzat per a latència baixa)."""
        ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Vectoritza N passatges (optimitzat per a throughput en batch)."""
        ...


class LLMInterface(Protocol):
    """Contracte del LLM que genera respostes amb cites verificables."""

    def generate(
        self,
        system_prompt: str,
        user_query: str,
        context: str,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        """Genera una resposta basada estrictament en el context recuperat."""
        ...

    def generate_suggestions(
        self,
        system_prompt: str,
        user_query: str,
        answer: str,
        context: str,
    ) -> list[str]:
        """Crida SEPARADA i garantida per a fins a 3 preguntes de seguiment.

        Independent de generate(): no depèn que la resposta llarga i citada
        arribi a incloure el bloc de suggeriments abans de truncar-se. Si
        falla, ha de retornar [] (mai trencar el torn de xat)."""
        ...

"""Interfícies del domini. Implementades per adaptadors a infrastructure/."""
from __future__ import annotations
from typing import Iterator, Protocol, Sequence

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


class LexicalSearchInterface(Protocol):
    """Contracte de la cerca lèxica (BM25 local, sense API externa) per a la
    cerca híbrida: complementa la cerca semàntica trobant coincidències de
    paraula exactes (noms propis, títols concrets) que l'embedding pot perdre."""

    def search_bm25(
        self,
        query: str,
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Cerca BM25 top-k, opcionalment filtrada per autor. Ha de degradar
        amb gràcia (retornar []) si la consulta no dona cap coincidència, mai
        trencar el retrieval."""
        ...


class RerankerInterface(Protocol):
    """Contracte del reordenador de candidats de retrieval (cross-encoder local,
    sense cap crida a API externa)."""

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Reordena `candidates` per rellevància real query+passatge (més precís
        que la similitud d'embeddings, que compara els dos per separat) i
        retorna els `top_k` millors. Si falla, ha de degradar amb gràcia
        (retornar els primers top_k sense reordenar, mai trencar el retrieval)."""
        ...


# Missatge que un adaptador LLM retorna quan no respon després dels reintents
# (saturat / quota exhaurida). Definit al DOMINI (no a infrastructure/llm.py)
# perquè tant l'adaptador que el produeix com ChatService que l'ha de
# RECONÈIXER (per no mostrar fonts/suggeriments d'una resposta que en
# realitat no existeix) hi puguin accedir sense que services depengui
# d'infrastructure. Trilingüe: encara no sabem l'idioma de la pregunta a
# aquest nivell (l'LLM ha fallat abans de poder-lo detectar).
LLM_BUSY_MSG = (
    "⏳ El servei està rebent moltes peticions ara mateix; torna-ho a provar d'aquí uns segons.\n"
    "⏳ El servicio está recibiendo muchas peticiones; inténtalo de nuevo en unos segundos.\n"
    "⏳ The service is busy right now; please try again in a few seconds."
)


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

    def generate_stream(
        self,
        system_prompt: str,
        user_query: str,
        context: str,
        history: list[tuple[str, str]] | None = None,
    ) -> Iterator[str]:
        """Com generate(), però en streaming: itera fragments de text incrementals
        a mesura que el model els genera, per reduir la latència PERCEBUDA (el
        contingut real de la resposta és idèntic, es reben els mateixos tokens)."""
        ...

    def generate_suggestions(
        self,
        system_prompt: str,
        user_query: str,
        answer: str,
        sources: str,
    ) -> list[str]:
        """Crida SEPARADA i garantida per a fins a 3 preguntes de seguiment.

        Independent de generate(): no depèn que la resposta llarga i citada
        arribi a incloure el bloc de suggeriments abans de truncar-se. Si
        falla, ha de retornar [] (mai trencar el torn de xat). `sources` és
        la llista compacta "Autor — Obra", NO els fragments de text sencers."""
        ...

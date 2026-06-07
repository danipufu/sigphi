"""SentenceTransformersEmbedder: model d'embeddings multilingüe local."""
from __future__ import annotations
import threading


class SentenceTransformersEmbedder:
    """Adaptador local de sentence-transformers (CPU-only).

    - Multilingüe: paraphrase-multilingual-MiniLM-L12-v2 (384-dim, 50+ idiomes).
    - device="cpu": el VPS no té GPU; torch CPU-only estalvia ~2.5 GB de CUDA.
    - torch.set_num_threads(2): limita els fils als 2 cores del VPS.
    - _lock: SentenceTransformer.encode no és thread-safe; serialitzem accessos
      perquè FastAPI pot rebre peticions concurrents amb 1 sol model en RAM.
    - normalize_embeddings=True: vectors unitaris -> cosine == dot product.
    """

    def __init__(self, model_name: str) -> None:
        import torch
        torch.set_num_threads(2)
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device="cpu")
        self._dim = int(self._model.get_sentence_embedding_dimension())
        self._lock = threading.Lock()

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            vec = self._model.encode(
                text,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return vec.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._lock:
            vecs = self._model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return vecs.tolist()

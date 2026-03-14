from __future__ import annotations

import os
from typing import Protocol


DEFAULT_EMBEDDING_MODEL = os.getenv(
    "SOUSCHEF_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [embedding.tolist() for embedding in embeddings]

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        embedding = model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embedding.tolist()

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for RAG embeddings. "
                    "Install backend requirements before using the RAG pipeline."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

from __future__ import annotations

import math
from collections.abc import Callable

from .chunking import RecipeChunk


class FaissVectorStore:
    def __init__(self) -> None:
        self._chunks: list[RecipeChunk] = []
        self._embeddings: list[list[float]] = []
        self._index = None
        self._faiss = None
        self._dimension: int | None = None

    def clear(self) -> None:
        self._chunks = []
        self._embeddings = []
        self._index = None
        self._dimension = None

    def add(self, chunks: list[RecipeChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings must have the same length.")
        if not chunks:
            return

        dimension = len(embeddings[0])
        if dimension == 0:
            raise ValueError("Embeddings must not be empty.")
        if any(len(embedding) != dimension for embedding in embeddings):
            raise ValueError("All embeddings must have the same dimension.")

        self.clear()
        self._chunks = list(chunks)
        self._embeddings = [list(embedding) for embedding in embeddings]
        self._dimension = dimension

        faiss = self._try_import_faiss()
        if faiss is None:
            return

        vectors = self._to_faiss_array(self._embeddings)
        index = faiss.IndexFlatIP(dimension)
        index.add(vectors)
        self._faiss = faiss
        self._index = index

    def search(
        self,
        query_embedding: list[float],
        *,
        limit: int = 4,
        recipe_id: str | None = None,
        score_adjuster: Callable[[RecipeChunk, float], float] | None = None,
    ) -> list[tuple[RecipeChunk, float]]:
        if not self._chunks:
            return []
        if self._dimension is None or len(query_embedding) != self._dimension:
            raise ValueError("Query embedding dimension does not match the index.")

        candidate_pairs = [
            (chunk, embedding)
            for chunk, embedding in zip(self._chunks, self._embeddings, strict=False)
            if recipe_id is None or chunk.recipe_id == recipe_id
        ]
        if not candidate_pairs:
            return []

        if recipe_id is None and score_adjuster is None and self._index is not None and self._faiss is not None:
            query_vector = self._to_faiss_array([query_embedding])
            distances, indices = self._index.search(query_vector, min(limit, len(self._chunks)))
            results: list[tuple[RecipeChunk, float]] = []
            for score, idx in zip(distances[0], indices[0], strict=False):
                if idx < 0:
                    continue
                results.append((self._chunks[int(idx)], float(score)))
            return results

        scored = []
        for chunk, embedding in candidate_pairs:
            score = _cosine_similarity(query_embedding, embedding)
            if score_adjuster is not None:
                score = score_adjuster(chunk, score)
            scored.append((chunk, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    @staticmethod
    def _try_import_faiss():
        try:
            import faiss
        except ImportError:
            return None
        return faiss

    @staticmethod
    def _to_faiss_array(vectors: list[list[float]]):
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "numpy is required when using the FAISS-backed vector store."
            ) from exc
        return np.asarray(vectors, dtype="float32")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)

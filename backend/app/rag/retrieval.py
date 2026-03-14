from __future__ import annotations

from pydantic import BaseModel, Field

from .chunking import RecipeChunk
from .embeddings import EmbeddingProvider
from .vector_store import FaissVectorStore


class RetrievalResult(BaseModel):
    chunk: RecipeChunk
    score: float


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievalResult] = Field(default_factory=list)


class RecipeRetriever:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        vector_store: FaissVectorStore | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store or FaissVectorStore()
        self._indexed_chunks: list[RecipeChunk] = []

    @property
    def indexed_count(self) -> int:
        return len(self._indexed_chunks)

    def index(self, chunks: list[RecipeChunk]) -> None:
        self._indexed_chunks = list(chunks)
        embeddings = self.embedder.embed_texts([chunk.text for chunk in chunks])
        self.vector_store.add(chunks, embeddings)

    def retrieve(self, query: str, *, limit: int = 4) -> RetrievalResponse:
        if not self._indexed_chunks:
            return RetrievalResponse(query=query, results=[])

        query_embedding = self.embedder.embed_query(query)
        matches = self.vector_store.search(query_embedding, limit=limit)
        return RetrievalResponse(
            query=query,
            results=[
                RetrievalResult(chunk=chunk, score=score)
                for chunk, score in matches
            ],
        )

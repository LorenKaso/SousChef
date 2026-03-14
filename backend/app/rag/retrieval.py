from __future__ import annotations

from pydantic import BaseModel, Field

from .chunking import RecipeChunk
from .embeddings import EmbeddingProvider
from .vector_store import FaissVectorStore


class RetrievalResult(BaseModel):
    chunk: RecipeChunk
    score: float


class RetrievalContext(BaseModel):
    session_id: str | None = None
    recipe_id: str | None = None
    section_index: int | None = None
    phase: str | None = None


class RetrievalResponse(BaseModel):
    query: str
    context: RetrievalContext | None = None
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

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 4,
        context: RetrievalContext | None = None,
    ) -> RetrievalResponse:
        if not self._indexed_chunks:
            return RetrievalResponse(query=query, context=context, results=[])

        query_embedding = self.embedder.embed_query(query)
        matches = self.vector_store.search(
            query_embedding,
            limit=limit,
            recipe_id=context.recipe_id if context is not None else None,
            score_adjuster=self._build_score_adjuster(context),
        )
        return RetrievalResponse(
            query=query,
            context=context,
            results=[
                RetrievalResult(chunk=chunk, score=score)
                for chunk, score in matches
            ],
        )

    @staticmethod
    def _build_score_adjuster(context: RetrievalContext | None):
        if context is None:
            return None
        if context.section_index is None and context.phase is None:
            return None

        def adjust(chunk: RecipeChunk, base_score: float) -> float:
            score = base_score
            if context.section_index is not None:
                chunk_section = chunk.metadata.get("section_index")
                if chunk_section == context.section_index:
                    score += 0.15

            if context.phase is not None and chunk.chunk_type == context.phase:
                score += 0.1
            return score

        return adjust

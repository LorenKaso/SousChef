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
    question_type: str | None = None
    requested_section: str | None = None
    prefer_chunk_type: str | None = None
    suppress_session_bias: bool = False


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

    def clear(self) -> None:
        self._indexed_chunks = []
        self.vector_store.clear()

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
        if (
            context.section_index is None
            and context.phase is None
            and context.requested_section is None
            and context.prefer_chunk_type is None
        ):
            return None

        def adjust(chunk: RecipeChunk, base_score: float) -> float:
            score = base_score
            if not context.suppress_session_bias and context.section_index is not None:
                chunk_section = chunk.metadata.get("section_index")
                if chunk_section == context.section_index:
                    score += 0.15

            if not context.suppress_session_bias and context.phase is not None and chunk.chunk_type == context.phase:
                score += 0.1
            if context.prefer_chunk_type is not None and chunk.chunk_type == context.prefer_chunk_type:
                score += 0.15
            if context.requested_section is not None:
                section_name = chunk.metadata.get("section_name")
                if isinstance(section_name, str) and _section_matches(section_name, context.requested_section):
                    score += 0.35
            return score

        return adjust


def _section_matches(section_name: str, requested_section: str) -> bool:
    section_lower = section_name.lower()
    requested_lower = requested_section.lower()
    if requested_lower in section_lower:
        return True

    translated_sections = {
        "Batter": "הבלילה",
        "Cooking": "הבישול",
        "Cake": "העוגה",
        "Topping": "הציפוי",
        "Pasta": "הפסטה",
        "Sauce and Serving": "הרוטב וההגשה",
    }
    translated = translated_sections.get(section_name)
    if translated is None:
        return False

    normalized_requested = _normalize_hebrew_section_query(requested_section)
    normalized_translated = _normalize_hebrew_section_query(translated)
    return (
        normalized_requested in normalized_translated
        or normalized_translated in normalized_requested
    )


def _normalize_hebrew_section_query(value: str) -> str:
    import re

    normalized = value.strip()
    normalized = re.sub(r"^חלק\s+של\s+", "", normalized)
    normalized = re.sub(r"^ה", "", normalized)
    normalized = normalized.replace(" ו", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()

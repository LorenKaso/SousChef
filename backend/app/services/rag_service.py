from __future__ import annotations

from ..rag.answer_builder import GroundedAnswer, RagAnswerBuilder
from ..rag.chunking import RecipeChunk, chunk_recipe
from ..rag.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingProvider, SentenceTransformerEmbedder
from ..rag.retrieval import RecipeRetriever, RetrievalContext, RetrievalResponse
from ..rag.vector_store import FaissVectorStore
from .recipe_service import RecipeService
from .session_service import SessionService


class RagService:
    def __init__(
        self,
        *,
        recipe_service: RecipeService | None = None,
        session_service: SessionService | None = None,
        embedder: EmbeddingProvider | None = None,
        retriever: RecipeRetriever | None = None,
        answer_builder: RagAnswerBuilder | None = None,
    ) -> None:
        self.recipe_service = recipe_service or RecipeService()
        self.session_service = session_service or SessionService()
        self.embedder = embedder or SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
        self.retriever = retriever or RecipeRetriever(
            embedder=self.embedder,
            vector_store=FaissVectorStore(),
        )
        self.answer_builder = answer_builder or RagAnswerBuilder()

    def build_chunks(self) -> list[RecipeChunk]:
        chunks: list[RecipeChunk] = []
        for recipe in self.recipe_service.list_recipes():
            chunks.extend(chunk_recipe(recipe))
        return chunks

    def rebuild_index(self) -> list[RecipeChunk]:
        chunks = self.build_chunks()
        self.retriever.index(chunks)
        return chunks

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 4,
        recipe_id: str | None = None,
        session_id: str | None = None,
    ) -> RetrievalResponse:
        if self.retriever.indexed_count == 0:
            self.rebuild_index()
        context = self._build_context(recipe_id=recipe_id, session_id=session_id)
        return self.retriever.retrieve(query, limit=limit, context=context)

    def supports_question(self, query: str) -> bool:
        return self.answer_builder.supports_query(query)

    def answer_question(
        self,
        query: str,
        *,
        limit: int = 4,
        recipe_id: str | None = None,
        session_id: str | None = None,
    ) -> GroundedAnswer:
        retrieval = self.retrieve(
            query,
            limit=limit,
            recipe_id=recipe_id,
            session_id=session_id,
        )
        return self.answer_builder.build(query, retrieval)

    def invalidate_index(self) -> None:
        self.retriever.clear()

    def _build_context(
        self,
        *,
        recipe_id: str | None,
        session_id: str | None,
    ) -> RetrievalContext | None:
        session = None
        if session_id is not None:
            session = self.session_service.get_session(session_id)

        resolved_recipe_id = recipe_id
        section_index = None
        phase = None

        if session is not None:
            resolved_recipe_id = session.recipe_id
            section_index = session.current_section_index
            phase = session.current_phase

        if resolved_recipe_id is None and session_id is None:
            return None

        return RetrievalContext(
            session_id=session_id if session is not None else None,
            recipe_id=resolved_recipe_id,
            section_index=section_index,
            phase=phase,
        )

from __future__ import annotations

from ..rag.answer_builder import GroundedAnswer, RagAnswerBuilder
from ..rag.chunking import RecipeChunk, chunk_recipe
from ..rag.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingProvider, SentenceTransformerEmbedder
from ..rag.retrieval import RecipeRetriever, RetrievalContext, RetrievalResponse
from ..sample_data import ensure_sample_recipes
from ..rag.vector_store import FaissVectorStore
from .llm_service import LLMService
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
        llm_service: LLMService | None = None,
    ) -> None:
        self.recipe_service = recipe_service or RecipeService()
        self.session_service = session_service or SessionService()
        if recipe_service is None:
            ensure_sample_recipes(self.recipe_service)
        self.embedder = embedder or SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
        self.retriever = retriever or RecipeRetriever(
            embedder=self.embedder,
            vector_store=FaissVectorStore(),
        )
        self.answer_builder = answer_builder or RagAnswerBuilder()
        self.llm_service = llm_service if llm_service is not None else LLMService()

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
        query_intent = self.answer_builder.analyze_query(query)
        context = self._build_context(
            recipe_id=recipe_id,
            session_id=session_id,
            query=query,
            query_intent=query_intent,
        )
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
        use_llm: bool = False,
    ) -> GroundedAnswer:
        retrieval = self.retrieve(
            query,
            limit=limit,
            recipe_id=recipe_id,
            session_id=session_id,
        )
        if use_llm:
            llm_answer = self._try_llm_answer(query=query, retrieval=retrieval)
            if llm_answer is not None:
                return llm_answer
        return self.answer_builder.build(query, retrieval)

    def answer_question_with_llm(
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
        llm_answer = self._try_llm_answer(query=query, retrieval=retrieval)
        if llm_answer is not None:
            return llm_answer
        return self.answer_builder.build(query, retrieval)

    def invalidate_index(self) -> None:
        self.retriever.clear()

    def _try_llm_answer(
        self,
        *,
        query: str,
        retrieval: RetrievalResponse,
    ) -> GroundedAnswer | None:
        llm_service = self.llm_service
        if llm_service is None:
            return None
        if not llm_service.is_available():
            return None
        if not llm_service.has_useful_context(retrieval):
            return None
        try:
            return llm_service.generate_grounded_answer(
                question=query,
                retrieval=retrieval,
            )
        except Exception:
            return None

    def _build_context(
        self,
        *,
        recipe_id: str | None,
        session_id: str | None,
        query: str,
        query_intent,
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

        question_type = query_intent.question_type if query_intent is not None else None
        requested_section = query_intent.requested_section if query_intent is not None else None
        prefer_chunk_type = None
        suppress_session_bias = False

        if question_type == "section_ingredients":
            prefer_chunk_type = "ingredients"
            suppress_session_bias = True
        elif question_type == "ingredient_amount":
            prefer_chunk_type = "ingredients"
        elif question_type == "when_to_add":
            prefer_chunk_type = "steps"

        return RetrievalContext(
            session_id=session_id if session is not None else None,
            recipe_id=resolved_recipe_id,
            section_index=section_index,
            phase=phase,
            question_type=question_type,
            requested_section=requested_section,
            prefer_chunk_type=prefer_chunk_type,
            suppress_session_bias=suppress_session_bias,
        )

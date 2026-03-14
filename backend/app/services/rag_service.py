from __future__ import annotations

from ..rag.chunking import RecipeChunk, chunk_recipe
from ..rag.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingProvider, SentenceTransformerEmbedder
from ..rag.retrieval import RecipeRetriever, RetrievalResponse
from ..rag.vector_store import FaissVectorStore
from .recipe_service import RecipeService


class RagService:
    def __init__(
        self,
        *,
        recipe_service: RecipeService | None = None,
        embedder: EmbeddingProvider | None = None,
        retriever: RecipeRetriever | None = None,
    ) -> None:
        self.recipe_service = recipe_service or RecipeService()
        self.embedder = embedder or SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
        self.retriever = retriever or RecipeRetriever(
            embedder=self.embedder,
            vector_store=FaissVectorStore(),
        )

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
    ) -> RetrievalResponse:
        if self.retriever.indexed_count == 0:
            self.rebuild_index()
        return self.retriever.retrieve(query, limit=limit, recipe_id=recipe_id)

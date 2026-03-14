from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.models import Ingredient, Recipe, RecipeSection, Step
from app.rag.chunking import chunk_recipe
from app.rag.retrieval import RecipeRetriever
from app.services.rag_service import RagService
from app.store import store


class KeywordEmbedder:
    def __init__(self) -> None:
        self.model_name = "test-keyword-embedder"
        self._features = [
            "mushroom",
            "pasta",
            "cake",
            "chocolate",
            "flour",
            "sugar",
            "cream",
            "parmesan",
            "simmer",
        ]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(feature)) for feature in self._features]


def setup_function() -> None:
    init_db()
    store.clear()
    seed_sample_recipe()


def test_chunk_recipe_emits_summary_ingredients_and_steps_chunks() -> None:
    recipe = Recipe(
        id="recipe-rag-basic",
        title="Basic Soup",
        servings=2,
        sections=[
            RecipeSection(
                name="Main",
                ingredients=[
                    Ingredient(name="water", amount=2, unit="cup"),
                    Ingredient(name="salt", amount=1, unit="tsp"),
                ],
                steps=[
                    Step(index=1, text="Boil the water."),
                    Step(index=2, text="Add salt and simmer."),
                    Step(index=3, text="Serve hot."),
                ],
            )
        ],
    )

    chunks = chunk_recipe(recipe, steps_per_chunk=2)

    assert [chunk.chunk_type for chunk in chunks] == ["summary", "ingredients", "steps", "steps"]
    assert "Recipe title: Basic Soup." in chunks[0].text
    assert "Ingredients:" in chunks[1].text
    assert "Step 1: Boil the water." in chunks[2].text
    assert chunks[2].metadata["step_from"] == 1
    assert chunks[2].metadata["step_to"] == 2


def test_recipe_retriever_returns_recipe_chunks_ranked_by_query() -> None:
    client = TestClient(app)
    assert client.get("/recipes").status_code == 200

    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    indexed_chunks = rag_service.rebuild_index()
    assert indexed_chunks

    response = rag_service.retrieve("How do I cook mushroom pasta?", limit=3)

    assert response.results
    assert response.results[0].chunk.recipe_id == "recipe-mushroom-cream-pasta"
    assert "Mushroom Cream Pasta" in response.results[0].chunk.text


def test_recipe_retrieval_can_be_scoped_to_a_single_recipe() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )
    rag_service.rebuild_index()

    response = rag_service.retrieve(
        "chocolate cake",
        limit=3,
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert response.context is not None
    assert response.context.recipe_id == "recipe-mushroom-cream-pasta"
    assert response.results
    assert all(
        result.chunk.recipe_id == "recipe-mushroom-cream-pasta"
        for result in response.results
    )


def test_recipe_retrieval_remains_global_without_recipe_scope() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )
    rag_service.rebuild_index()

    response = rag_service.retrieve("chocolate cake", limit=3)

    assert response.context is None
    assert response.results
    assert response.results[0].chunk.recipe_id == "recipe-birthday-chocolate-cake"


def test_session_aware_retrieval_uses_active_recipe_context() -> None:
    session = store.session_service.start_session("recipe-mushroom-cream-pasta")

    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )
    rag_service.rebuild_index()

    response = rag_service.retrieve(
        "When do I add cream?",
        limit=3,
        session_id=session.id,
    )

    assert response.context is not None
    assert response.context.session_id == session.id
    assert response.context.recipe_id == "recipe-mushroom-cream-pasta"
    assert response.results
    assert all(
        result.chunk.recipe_id == "recipe-mushroom-cream-pasta"
        for result in response.results
    )


def test_session_context_prefers_current_section_and_phase() -> None:
    session = store.session_service.start_session("recipe-mushroom-cream-pasta")
    session.current_section_index = 1
    session.current_phase = "steps"
    session.current_item_index = 1
    store.sessions[session.id] = session

    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )
    rag_service.rebuild_index()

    response = rag_service.retrieve(
        "When do I add cream and parmesan?",
        limit=3,
        session_id=session.id,
    )

    assert response.context is not None
    assert response.context.section_index == 1
    assert response.context.phase == "steps"
    assert response.results
    assert response.results[0].chunk.recipe_id == "recipe-mushroom-cream-pasta"
    assert response.results[0].chunk.chunk_type == "steps"
    assert response.results[0].chunk.metadata["section_index"] == 1


def test_retriever_handles_empty_index() -> None:
    retriever = RecipeRetriever(embedder=KeywordEmbedder())

    response = retriever.retrieve("find cake")

    assert response.query == "find cake"
    assert response.context is None
    assert response.results == []

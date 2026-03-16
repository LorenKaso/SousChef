from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.models import Ingredient, Recipe, RecipeSection, Step
from app.rag.chunking import chunk_recipe
from app.rag.retrieval import RecipeRetriever
from app.services.llm_service import LLMService, build_grounded_answer_prompt
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


class FakeLLMProvider:
    def __init__(self) -> None:
        self.model_name = "fake-llm"
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Grounded answer from fake LLM."


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


def test_grounded_answer_formats_when_to_add_question_from_session_context() -> None:
    session = store.session_service.start_session("recipe-mushroom-cream-pasta")
    session.current_section_index = 1
    session.current_phase = "steps"
    store.sessions[session.id] = session

    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question("When do I add cream?", session_id=session.id)

    assert answer.answer_type == "when_to_add"
    assert (
        answer.answer
        == "You add the cream in the Sauce and Serving section, together with parmesan and black pepper."
    )
    assert answer.sources


def test_grounded_answer_formats_ingredient_amount_question() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "How much pasta is in the recipe?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "ingredient_amount"
    assert answer.answer == "This recipe uses 400 g of pasta."
    assert answer.sources


def test_grounded_answer_formats_section_ingredients_question() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "What is in the sauce and serving?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "section_ingredients"
    assert (
        answer.answer
        == "The sauce and serving section includes mushroom, cream, butter, parmesan, and black pepper."
    )
    assert answer.sources


def test_grounded_answer_formats_section_ingredients_question_with_goes_in_variant() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "What goes in the sauce?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "section_ingredients"
    assert (
        answer.answer
        == "The sauce and serving section includes mushroom, cream, butter, parmesan, and black pepper."
    )
    assert answer.sources


def test_grounded_answer_formats_hebrew_ingredient_amount_question() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "כמה פסטה יש במתכון?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "ingredient_amount"
    assert answer.answer == "במתכון יש 400 גרם פסטה."
    assert answer.sources


def test_grounded_answer_formats_hebrew_when_to_add_question() -> None:
    session = store.session_service.start_session("recipe-mushroom-cream-pasta")
    session.current_section_index = 1
    session.current_phase = "steps"
    store.sessions[session.id] = session

    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question("מתי מוסיפים שמנת?", session_id=session.id)

    assert answer.answer_type == "when_to_add"
    assert (
        answer.answer
        == "מוסיפים את השמנת בחלק של הרוטב וההגשה, יחד עם פרמזן ופלפל שחור."
    )
    assert answer.sources


def test_grounded_answer_formats_hebrew_section_ingredients_question() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "מה יש ברוטב?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "section_ingredients"
    assert answer.answer == "בחלק של הרוטב וההגשה יש פטריות, שמנת, חמאה, פרמזן ופלפל שחור."
    assert answer.sources


def test_hebrew_section_question_overrides_current_section_bias() -> None:
    session = store.session_service.start_session("recipe-mushroom-cream-pasta")
    session.current_section_index = 0
    session.current_phase = "ingredients"
    store.sessions[session.id] = session

    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )
    response = rag_service.retrieve(
        "\u05de\u05d4 \u05d9\u05e9 \u05d1\u05e8\u05d5\u05d8\u05d1?",
        session_id=session.id,
    )

    assert response.context is not None
    assert response.context.suppress_session_bias is True
    assert response.context.requested_section == "\u05e8\u05d5\u05d8\u05d1"
    assert response.results
    assert response.results[0].chunk.chunk_type == "ingredients"
    assert response.results[0].chunk.metadata["section_name"] == "Sauce and Serving"

    answer = rag_service.answer_question(
        "\u05de\u05d4 \u05d9\u05e9 \u05d1\u05e8\u05d5\u05d8\u05d1?",
        session_id=session.id,
    )

    assert answer.answer_type == "section_ingredients"
    assert (
        answer.answer
        == "\u05d1\u05d7\u05dc\u05e7 \u05e9\u05dc \u05d4\u05e8\u05d5\u05d8\u05d1 "
        "\u05d5\u05d4\u05d4\u05d2\u05e9\u05d4 \u05d9\u05e9 \u05e4\u05d8\u05e8\u05d9\u05d5\u05ea, "
        "\u05e9\u05de\u05e0\u05ea, \u05d7\u05de\u05d0\u05d4, \u05e4\u05e8\u05de\u05d6\u05df "
        "\u05d5\u05e4\u05dc\u05e4\u05dc \u05e9\u05d7\u05d5\u05e8."
    )


def test_grounded_answer_formats_hebrew_section_name_variant() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "מה יש בחלק של הרוטב וההגשה?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "section_ingredients"
    assert answer.answer == "בחלק של הרוטב וההגשה יש פטריות, שמנת, חמאה, פרמזן ופלפל שחור."
    assert answer.sources


def test_grounded_answer_falls_back_to_clean_chunk_when_not_confident() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "Tell me something useful about the batter.",
        recipe_id="recipe-basic-pancakes",
    )

    assert answer.answer_type == "fallback_chunk"
    assert "Relevant note" in answer.answer
    assert answer.sources


def test_grounded_answer_hebrew_fallback_remains_grounded() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )

    answer = rag_service.answer_question(
        "תגיד משהו מועיל על הבלילה",
        recipe_id="recipe-basic-pancakes",
    )

    assert answer.answer_type == "fallback_chunk"
    assert "הערה רלוונטית" in answer.answer
    assert answer.sources


def test_retriever_handles_empty_index() -> None:
    retriever = RecipeRetriever(embedder=KeywordEmbedder())

    response = retriever.retrieve("find cake")

    assert response.query == "find cake"
    assert response.context is None
    assert response.results == []


def test_llm_prompt_builder_includes_question_context_and_grounding_rules() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
    )
    retrieval = rag_service.retrieve(
        "How much pasta is in the recipe?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    prompt = build_grounded_answer_prompt(
        question="How much pasta is in the recipe?",
        retrieval=retrieval,
        answer_language="en",
    )

    assert "Use only the provided context." in prompt
    assert "Do not invent recipe details" in prompt
    assert "How much pasta is in the recipe?" in prompt
    assert "recipe-mushroom-cream-pasta" in prompt
    assert "400 g pasta" in prompt


def test_llm_service_returns_safe_fallback_when_context_is_missing() -> None:
    llm_service = LLMService()
    retriever = RecipeRetriever(embedder=KeywordEmbedder())
    retrieval = retriever.retrieve("How much pasta is in the recipe?")

    answer = llm_service.generate_grounded_answer(
        question="How much pasta is in the recipe?",
        retrieval=retrieval,
    )

    assert answer.answer_type == "llm_no_context"
    assert answer.sources == []
    assert "enough grounded recipe context" in answer.answer


def test_rag_service_exposes_optional_llm_answer_path() -> None:
    provider = FakeLLMProvider()
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
        llm_service=LLMService(provider),
    )

    answer = rag_service.answer_question_with_llm(
        "How much pasta is in the recipe?",
        recipe_id="recipe-mushroom-cream-pasta",
    )

    assert answer.answer_type == "llm_grounded"
    assert answer.answer == "Grounded answer from fake LLM."
    assert answer.sources
    assert provider.prompts


def test_rag_service_falls_back_to_deterministic_answer_when_llm_is_disabled() -> None:
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
        llm_service=LLMService(),
    )

    answer = rag_service.answer_question(
        "How much pasta is in the recipe?",
        recipe_id="recipe-mushroom-cream-pasta",
        use_llm=True,
    )

    assert answer.answer_type == "ingredient_amount"
    assert answer.answer == "This recipe uses 400 g of pasta."


def test_rag_service_falls_back_to_deterministic_answer_when_context_is_missing() -> None:
    provider = FakeLLMProvider()
    rag_service = RagService(
        recipe_service=store.recipe_service,
        embedder=KeywordEmbedder(),
        llm_service=LLMService(provider),
    )

    answer = rag_service.answer_question_with_llm(
        "How much dragonfruit is in the recipe?",
        recipe_id="recipe-missing",
    )

    assert answer.answer_type == "no_match"
    assert "grounded recipe answer" in answer.answer

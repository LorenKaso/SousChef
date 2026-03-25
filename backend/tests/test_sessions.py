from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.models import Ingredient, Recipe, RecipeSection, Step, Timer
from app.services.llm_service import LLMService
from app.services.rag_service import RagService
from app.store import store

HE_WHAT_NOW = "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5"
HE_NEXT_STEP = "\u05e9\u05dc\u05d1 \u05d4\u05d1\u05d0"
HE_DONE = "\u05e9\u05de\u05ea\u05d9"
TIME_LEFT_TEXT = "time left"


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
            "פסטה",
            "שמנת",
            "פרמזן",
            "רוטב",
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
        return "LLM grounded answer."


class FakeFailingLLMProvider:
    def __init__(self) -> None:
        self.model_name = "fake-failing-llm"

    def generate(self, prompt: str) -> str:
        raise RuntimeError("provider failure")


def setup_function() -> None:
    init_db()
    store.clear()
    seed_sample_recipe()


def _start_session(client: TestClient, recipe_id: str) -> str:
    response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert response.status_code == 200
    return response.json()["id"]


def _add_recipe(recipe: Recipe) -> str:
    store.add_recipe(recipe)
    return recipe.id


def _configure_test_rag_service(*, with_llm: bool = False) -> FakeLLMProvider | None:
    provider = FakeLLMProvider() if with_llm else None
    llm_service = LLMService(provider) if with_llm else LLMService()
    if not with_llm:
        llm_service.provider = None
    store.rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
        llm_service=llm_service,
    )
    return provider


def test_what_now_does_not_advance_but_next_step_does() -> None:
    """מה עכשיו (what now) shows the current item without advancing.
    שלב הבא / מה השלב הבא (next step) must advance to the next item.
    """
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    first_response = client.post(
        f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW}
    )
    assert first_response.status_code == 200
    assert (
        first_response.headers["content-type"]
        == "application/json; charset=utf-8"
    )
    first_payload = first_response.json()
    # Batter section now uses flow mode; answer includes a "next" preview.
    assert first_payload["answer"].startswith(
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )
    assert first_payload["session"]["current_section_index"] == 0
    assert first_payload["session"]["current_phase"] == "flow"
    assert first_payload["session"]["current_item_index"] == 0

    # Repeating "what now" must not advance — still item 0.
    repeated_response = client.post(
        f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW}
    )
    assert repeated_response.status_code == 200
    repeated_payload = repeated_response.json()
    assert repeated_payload["answer"] == first_payload["answer"]
    assert repeated_payload["session"]["current_item_index"] == 0

    # "שלב הבא" (next step) must advance — now item 1.
    next_response = client.post(
        f"/session/{session_id}/ask", json={"text": HE_NEXT_STEP}
    )
    assert next_response.status_code == 200
    next_payload = next_response.json()
    assert next_payload["answer"] != first_payload["answer"]
    assert next_payload["session"]["current_item_index"] == 1


def test_english_next_advances_progression_while_what_now_stays_read_only() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    show_response = client.post(f"/session/{session_id}/ask", json={"text": "what now"})
    assert show_response.status_code == 200
    # Flow mode: answer includes "Next: ..." preview
    assert show_response.json()["answer"].startswith("Add 1 cup of flour.")
    assert show_response.json()["session"]["current_item_index"] == 0

    next_response = client.post(f"/session/{session_id}/ask", json={"text": "next"})
    assert next_response.status_code == 200
    next_payload = next_response.json()
    # Flow order: flour(0) -> sugar(1) -> milk(2) -> step(3)
    assert next_payload["answer"].startswith("Add 1 tbsp of sugar.")
    assert next_payload["session"]["current_item_index"] == 1

    repeat_response = client.post(f"/session/{session_id}/ask", json={"text": "what's next"})
    assert repeat_response.status_code == 200
    repeat_payload = repeat_response.json()
    assert repeat_payload["answer"].startswith("Add 1 tbsp of sugar.")
    assert repeat_payload["session"]["current_item_index"] == 1


def test_hebrew_completion_command_advances_in_api_flow() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    # Send Hebrew commands as JSON so the request body stays UTF-8 encoded.
    first_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert first_response.status_code == 200
    # Flow mode: answer for flour includes "next" preview
    HE_FLOUR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )
    assert first_response.json()["answer"].startswith(HE_FLOUR)

    done_response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert done_response.status_code == 200
    # Flow order: flour(0) -> sugar(1); sugar answer starts with sugar text
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )
    assert done_response.json()["answer"].startswith(HE_SUGAR)

    second_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert second_response.status_code == 200
    assert second_response.json()["answer"].startswith(HE_SUGAR)
    assert second_response.json()["session"]["current_item_index"] == 1


def test_all_supported_hebrew_completion_commands_advance_api_flow() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    completion_commands = [
        "\u05e9\u05de\u05ea\u05d9",
        "\u05d4\u05d5\u05e1\u05e4\u05ea\u05d9",
        "\u05e1\u05d9\u05d9\u05de\u05ea\u05d9",
    ]

    # Flow order: flour(0) -> sugar(1). After one "done" we reach sugar.
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )

    for command in completion_commands:
        session_id = _start_session(client, recipe_id)
        client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})

        done_response = client.post(f"/session/{session_id}/ask", json={"text": command})
        assert done_response.status_code == 200
        assert done_response.json()["answer"].startswith(HE_SUGAR)
        assert done_response.json()["session"]["current_item_index"] == 1
        assert done_response.json()["session"]["current_phase"] == "flow"


def test_mushroom_pasta_guidance_is_localized_in_hebrew_and_english() -> None:
    client = TestClient(app)
    recipes = client.get("/recipes").json()
    recipe_id = next(recipe["id"] for recipe in recipes if recipe["id"] == "recipe-mushroom-cream-pasta")
    session_id = _start_session(client, recipe_id)

    hebrew_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert hebrew_response.status_code == 200
    assert "\u05e4\u05e1\u05d8\u05d4" in hebrew_response.json()["answer"]

    store.sessions.pop(session_id)
    session_id = _start_session(client, recipe_id)

    english_response = client.post(f"/session/{session_id}/ask", json={"text": "what now?"})
    assert english_response.status_code == 200
    assert "pasta" in english_response.json()["answer"].lower()


def test_completion_advances_ingredients_then_steps_then_next_section() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    # Batter flow: flour(0) -> sugar(1) -> milk(2) -> mix-step(3)
    # Cooking flow: oil(0) -> heat-pan-step(1) -> pour-step(2)
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )
    HE_MILK = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05d5\u05e1 \u05d7\u05dc\u05d1."
    )
    HE_OIL = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e9\u05de\u05df."
    )

    first_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert first_done.status_code == 200
    # flour -> sugar (item 0 -> item 1)
    assert first_done.json()["answer"].startswith(HE_SUGAR)

    second_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert second_done.status_code == 200
    # sugar -> milk (item 1 -> item 2)
    assert second_done.json()["answer"].startswith(HE_MILK)

    third_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert third_done.status_code == 200
    third_payload = third_done.json()
    # milk -> mix step (item 2 -> item 3, last in Batter; no preview)
    assert third_payload["answer"] == "Mix flour, sugar, and milk into a smooth batter."
    assert third_payload["session"]["current_phase"] == "flow"
    assert third_payload["session"]["current_item_index"] == 3

    fourth_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert fourth_done.status_code == 200
    fourth_payload = fourth_done.json()
    # mix step -> Cooking section, oil (item 0)
    assert fourth_payload["answer"].startswith(HE_OIL)
    assert fourth_payload["session"]["current_section_index"] == 1
    assert fourth_payload["session"]["current_phase"] == "flow"
    assert fourth_payload["session"]["current_item_index"] == 0


def test_final_completion_returns_clear_recipe_message() -> None:
    client = TestClient(app)
    recipe = client.get("/recipes").json()[0]
    recipe_id = recipe["id"]
    session_id = _start_session(client, recipe_id)
    total_guided_items = sum(
        len(section["ingredients"]) + len(section["steps"])
        for section in recipe["sections"]
    )

    for _ in range(total_guided_items):
        response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
        assert response.status_code == 200

    payload = response.json()
    assert (
        payload["answer"]
        == "\u05e1\u05d9\u05d9\u05de\u05ea \u05d0\u05ea \u05db\u05dc \u05d4\u05de\u05ea\u05db\u05d5\u05df."
    )
    assert payload["session"]["current_section_index"] == 2
    assert payload["session"]["current_phase"] == "steps"
    assert payload["session"]["current_item_index"] == 0


def test_section_with_no_ingredients_transitions_to_steps() -> None:
    recipe_id = _add_recipe(
        Recipe(
            id="recipe-no-ingredients",
            title="No Ingredients First",
            servings=1,
            sections=[
                RecipeSection(
                    name="Bake",
                    ingredients=[],
                    steps=[Step(index=1, text="Bake until golden.")],
                )
            ],
        )
    )
    client = TestClient(app)
    session_id = _start_session(client, recipe_id)

    response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Bake until golden."
    assert payload["session"]["current_phase"] == "steps"
    assert payload["session"]["current_item_index"] == 0


def test_section_with_no_steps_moves_directly_to_next_section() -> None:
    recipe_id = _add_recipe(
        Recipe(
            id="recipe-no-steps",
            title="No Steps Section",
            servings=1,
            sections=[
                RecipeSection(
                    name="Prep",
                    ingredients=[Ingredient(name="salt", amount=1, unit="tsp")],
                    steps=[],
                ),
                RecipeSection(
                    name="Cook",
                    ingredients=[Ingredient(name="oil", amount=1, unit="tbsp")],
                    steps=[Step(index=1, text="Cook gently.")],
                ),
            ],
        )
    )
    client = TestClient(app)
    session_id = _start_session(client, recipe_id)

    response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05e3 \u05e9\u05de\u05df."
    )
    assert payload["session"]["current_section_index"] == 1
    assert payload["session"]["current_phase"] == "ingredients"
    assert payload["session"]["current_item_index"] == 0


def test_session_expires_after_ttl(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "1")
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    session = store.sessions[session_id]
    session.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    store.sessions[session_id] = session

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert ask_response.status_code == 404


def test_session_not_expired_if_recent(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "10")
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert ask_response.status_code == 200


def test_expired_timers_removed() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    session = store.sessions[session_id]
    session.active_timers.append(
        Timer(
            seconds=1,
            label="Old timer",
            step_index=1,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
    )
    store.sessions[session_id] = session

    current = store.get_session(session_id)
    assert current is not None
    assert current.active_timers == []


def test_time_left_no_timer() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": TIME_LEFT_TEXT})
    assert ask_response.status_code == 200
    answer = ask_response.json()["answer"]
    assert re.search(r"^No active timer\.$", answer)


def test_time_left_active_timer() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    start_timer_response = client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    assert start_timer_response.status_code == 200

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": TIME_LEFT_TEXT})
    assert ask_response.status_code == 200
    answer = ask_response.json()["answer"]
    match = re.search(r"^Time left: \d+ (?:seconds|minutes|hours)\.$", answer)
    assert match is not None


def test_time_left_timer_finished(monkeypatch) -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    start_timer_response = client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    assert start_timer_response.status_code == 200

    session = store.sessions[session_id]
    assert session.active_timers
    session.active_timers[-1].started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    store.sessions[session_id] = session

    monkeypatch.setattr(store.session_service, "_prune_expired_timers", lambda _session, _now: None)

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": TIME_LEFT_TEXT})
    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert payload["answer"] == "Timer finished."
    action_types = [action["type"] for action in payload["actions"]]
    assert "TIMER_FINISHED" in action_types


def test_session_persists_across_repository_reload() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    advance_response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert advance_response.status_code == 200

    reloaded_session = store.session_repository.get(session_id)
    assert reloaded_session is not None
    assert reloaded_session.current_item_index == 1
    assert reloaded_session.current_phase == "flow"


def test_time_left_english_response_shape() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    ask_response = client.post(f"/session/{session_id}/ask", json={"text": "time left"})
    assert ask_response.status_code == 200

    answer = ask_response.json()["answer"]
    assert re.search(r"^Time left: \d+ (?:seconds|minutes|hours)\.$", answer)


def test_command_routing_still_uses_deterministic_progression() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert response.status_code == 200
    payload = response.json()
    # Flow order flour(0)->sugar(1); answer may include "next" preview
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )
    assert payload["answer"].startswith(HE_SUGAR)
    assert payload["session"]["current_item_index"] == 1


def test_main_ask_routes_english_recipe_question_to_grounded_rag_answer() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "When do I add cream?"})

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "You add the cream in the Sauce and Serving section, together with parmesan and black pepper."
    )
    assert payload["actions"] == []
    # RAG answer does not advance the session; phase is still the initial value
    assert payload["session"]["current_phase"] == "ingredients"
    assert payload["session"]["current_item_index"] == 0


def test_main_ask_routes_hebrew_recipe_question_to_grounded_rag_answer() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "כמה פסטה יש במתכון?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "במתכון יש 400 גרם פסטה."
    assert payload["actions"] == []


def test_main_ask_uses_session_aware_rag_answering() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    session = store.sessions[session_id]
    session.current_section_index = 1
    session.current_phase = "steps"
    store.sessions[session_id] = session

    response = client.post(f"/session/{session_id}/ask", json={"text": "מה יש ברוטב?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "בחלק של הרוטב וההגשה יש פטריות, שמנת, חמאה, פרמזן ופלפל שחור."
    assert payload["actions"] == []
    assert payload["session"]["current_section_index"] == 1
    assert payload["session"]["current_phase"] == "steps"


def test_main_ask_hebrew_section_question_overrides_current_section_preference() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    session = store.sessions[session_id]
    session.current_section_index = 0
    session.current_phase = "ingredients"
    store.sessions[session_id] = session

    response = client.post(
        f"/session/{session_id}/ask",
        json={"text": "\u05de\u05d4 \u05d9\u05e9 \u05d1\u05e8\u05d5\u05d8\u05d1?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "\u05d1\u05d7\u05dc\u05e7 \u05e9\u05dc \u05d4\u05e8\u05d5\u05d8\u05d1 "
        "\u05d5\u05d4\u05d4\u05d2\u05e9\u05d4 \u05d9\u05e9 \u05e4\u05d8\u05e8\u05d9\u05d5\u05ea, "
        "\u05e9\u05de\u05e0\u05ea, \u05d7\u05de\u05d0\u05d4, \u05e4\u05e8\u05de\u05d6\u05df "
        "\u05d5\u05e4\u05dc\u05e4\u05dc \u05e9\u05d7\u05d5\u05e8."
    )
    assert payload["actions"] == []
    assert payload["session"]["current_section_index"] == 0
    assert payload["session"]["current_phase"] == "ingredients"
    assert payload["session"]["current_item_index"] == 0


def test_main_ask_repairs_mojibake_hebrew_query_before_routing() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(
        f"/session/{session_id}/ask",
        json={"text": "×ž×” ×™×© ×‘×¨×•×˜×‘?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "בחלק של הרוטב וההגשה יש פטריות, שמנת, חמאה, פרמזן ופלפל שחור."


def test_main_ask_routes_what_goes_in_the_sauce_to_rag_instead_of_progression() -> None:
    _configure_test_rag_service()
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "what goes in the sauce?"})

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "The sauce and serving section includes mushroom, cream, butter, parmesan, and black pepper."
    )
    assert payload["actions"] == []
    assert payload["session"]["current_phase"] == "ingredients"
    assert payload["session"]["current_item_index"] == 0


def test_main_ask_can_use_grounded_llm_answer_for_recipe_questions() -> None:
    provider = _configure_test_rag_service(with_llm=True)
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "When do I add cream?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "LLM grounded answer."
    assert payload["actions"] == []
    assert provider is not None
    assert provider.prompts


def test_main_ask_falls_back_safely_when_llm_is_disabled() -> None:
    _configure_test_rag_service(with_llm=False)
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "When do I add cream?"})

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "You add the cream in the Sauce and Serving section, together with parmesan and black pepper."
    )
    assert payload["actions"] == []


def test_main_ask_falls_back_safely_when_llm_provider_fails() -> None:
    store.rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
        llm_service=LLMService(FakeFailingLLMProvider()),
    )
    client = TestClient(app)

    session_id = _start_session(client, "recipe-mushroom-cream-pasta")
    response = client.post(f"/session/{session_id}/ask", json={"text": "When do I add cream?"})

    assert response.status_code == 200
    payload = response.json()
    assert (
        payload["answer"]
        == "You add the cream in the Sauce and Serving section, together with parmesan and black pepper."
    )
    assert payload["actions"] == []


def test_wake_prefix_stripped_before_routing() -> None:
    """Assistant-name / wake-word prefixes must be transparent to question routing.

    "SousChef, what now"       → same as "what now"       → reads current item, no advance
    "So, next step"            → same as "next step"       → advances one item
    "סושף, מה עכשיו"           → same as "מה עכשיו"        → reads current item, no advance
    "סו, השלב הבא"             → same as "השלב הבא"        → advances one item
    "Sous Chef, what now"      → same as "what now"        → reads current item, no advance

    Answer language follows _detect_lang on the post-strip text: English
    inputs produce English answers; Hebrew inputs produce Hebrew answers.
    """
    # Hebrew flour / sugar — used when input text contains Hebrew chars.
    HE_FLOUR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    # ── "SousChef, what now" — English input → English answer ────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "SousChef, what now"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith("Add 1 cup of flour.")
    assert r.json()["session"]["current_item_index"] == 0

    # ── "So, next step" — English input → English answer, advances ───────────
    session_id = _start_session(client, recipe_id)
    client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    r = client.post(f"/session/{session_id}/ask", json={"text": "So, next step"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith("Add 1 tbsp of sugar.")
    assert r.json()["session"]["current_item_index"] == 1

    # ── "סושף, מה עכשיו" — Hebrew input → Hebrew answer, no advance ──────────
    session_id = _start_session(client, recipe_id)
    r = client.post(
        f"/session/{session_id}/ask",
        json={"text": "\u05e1\u05d5\u05e9\u05e3, \u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5"},
    )
    assert r.status_code == 200
    assert r.json()["answer"].startswith(HE_FLOUR)
    assert r.json()["session"]["current_item_index"] == 0

    # ── "סו, השלב הבא" — Hebrew input → Hebrew answer, advances ─────────────
    session_id = _start_session(client, recipe_id)
    client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    r = client.post(
        f"/session/{session_id}/ask",
        json={"text": "\u05e1\u05d5, \u05d4\u05e9\u05dc\u05d1 \u05d4\u05d1\u05d0"},
    )
    assert r.status_code == 200
    assert r.json()["answer"].startswith(HE_SUGAR)
    assert r.json()["session"]["current_item_index"] == 1

    # ── "Sous Chef, what now" — English input → English answer ───────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "Sous Chef, what now"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith("Add 1 cup of flour.")
    assert r.json()["session"]["current_item_index"] == 0


def test_filler_words_do_not_block_navigation_commands() -> None:
    """STT often prepends or appends filler tokens to navigation commands.

    All inputs are English so answers come back in English.

    "ok next step"       → same as "next step"    → advances one item
    "next, step"         → same as "next step"    → advances one item  (comma)
    "please what now"    → same as "what now"     → reads without advancing
    "what now please"    → same as "what now"     → reads without advancing
    "uh what's next"     → same as "what's next"  → reads without advancing
    """
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    EN_FLOUR = "Add 1 cup of flour."
    EN_SUGAR = "Add 1 tbsp of sugar."

    # ── "ok next step" → advances ────────────────────────────────────────────
    session_id = _start_session(client, recipe_id)
    client.post(f"/session/{session_id}/ask", json={"text": "what now"})
    r = client.post(f"/session/{session_id}/ask", json={"text": "ok next step"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith(EN_SUGAR)
    assert r.json()["session"]["current_item_index"] == 1

    # ── "next, step" (STT comma) → advances ──────────────────────────────────
    session_id = _start_session(client, recipe_id)
    client.post(f"/session/{session_id}/ask", json={"text": "what now"})
    r = client.post(f"/session/{session_id}/ask", json={"text": "next, step"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith(EN_SUGAR)
    assert r.json()["session"]["current_item_index"] == 1

    # ── "please what now" → reads without advancing ───────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "please what now"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith(EN_FLOUR)
    assert r.json()["session"]["current_item_index"] == 0

    # ── "what now please" → reads without advancing ───────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "what now please"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith(EN_FLOUR)
    assert r.json()["session"]["current_item_index"] == 0

    # ── "uh what's next" → reads without advancing ───────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "uh what's next"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith(EN_FLOUR)
    assert r.json()["session"]["current_item_index"] == 0


def test_hebrew_ingredient_mention_validates_against_current_item() -> None:
    """'שמתי X' must advance only when X matches the current guided item.

    - "שמתי קמח" when at flour  → advance (flour is current) ✓
    - "שמתי סוכר" when at flour → redirect back to flour     ✗
    - "שמתי" bare               → advance unconditionally    ✓ (no ingredient)
    """
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    HE_FLOUR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )
    HE_SUGAR = (
        "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3"
        " 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )

    # ── correct ingredient → advance to sugar ─────────────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(
        f"/session/{session_id}/ask",
        # "שמתי קמח" — I added flour
        json={"text": "\u05e9\u05de\u05ea\u05d9 \u05e7\u05de\u05d7"},
    )
    assert r.status_code == 200
    assert r.json()["answer"].startswith(HE_SUGAR)
    assert r.json()["session"]["current_item_index"] == 1

    # ── wrong ingredient → redirect back to flour ─────────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(
        f"/session/{session_id}/ask",
        # "שמתי סוכר" — I added sugar (but current is flour)
        json={"text": "\u05e9\u05de\u05ea\u05d9 \u05e1\u05d5\u05db\u05e8"},
    )
    assert r.status_code == 200
    # Answer should redirect to flour, not advance to sugar
    assert r.json()["answer"].endswith(HE_FLOUR) or HE_FLOUR in r.json()["answer"]
    assert r.json()["session"]["current_item_index"] == 0

    # ── bare "שמתי" (no ingredient named) → advance unconditionally ──────────
    session_id = _start_session(client, recipe_id)
    r = client.post(
        f"/session/{session_id}/ask",
        json={"text": HE_DONE},
    )
    assert r.status_code == 200
    assert r.json()["answer"].startswith(HE_SUGAR)
    assert r.json()["session"]["current_item_index"] == 1


def test_english_i_added_advances_when_ingredient_matches() -> None:
    """'I added X' (English) must validate against the current guided item.

    - "I added flour" when at flour → advance
    - "I added sugar" when at flour → redirect back to flour
    - "I added it"                  → advance unconditionally (no recipe ingredient)
    """
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    # ── "I added flour" when at flour → advance to sugar ──────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "I added flour"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith("Add 1 tbsp of sugar.")
    assert r.json()["session"]["current_item_index"] == 1

    # ── "I added sugar" when at flour → redirect ──────────────────────────────
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "I added sugar"})
    assert r.status_code == 200
    assert r.json()["answer"].startswith("Not yet") or "Add 1 cup of flour" in r.json()["answer"]
    assert r.json()["session"]["current_item_index"] == 0

    # ── "I added it" → "it" is not a recipe ingredient → advance via fallback ─
    session_id = _start_session(client, recipe_id)
    r = client.post(f"/session/{session_id}/ask", json={"text": "I added it"})
    assert r.status_code == 200
    assert r.json()["session"]["current_item_index"] == 1

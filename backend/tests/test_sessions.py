from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.models import Ingredient, Recipe, RecipeSection, Step, Timer
from app.store import store

HE_WHAT_NOW = "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5"
HE_NEXT_STEP = "\u05e9\u05dc\u05d1 \u05d4\u05d1\u05d0"
HE_DONE = "\u05e9\u05de\u05ea\u05d9"
TIME_LEFT_TEXT = "time left"


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


def test_query_commands_do_not_advance_guided_progress() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    first_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert (
        first_payload["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )
    assert first_payload["session"]["current_section_index"] == 0
    assert first_payload["session"]["current_phase"] == "ingredients"
    assert first_payload["session"]["current_item_index"] == 0

    repeated_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert repeated_response.status_code == 200
    repeated_payload = repeated_response.json()
    assert repeated_payload["answer"] == first_payload["answer"]
    assert repeated_payload["session"]["current_item_index"] == 0

    next_response = client.post(f"/session/{session_id}/ask", json={"text": HE_NEXT_STEP})
    assert next_response.status_code == 200
    next_payload = next_response.json()
    assert next_payload["answer"] == first_payload["answer"]
    assert next_payload["session"]["current_item_index"] == 0


def test_hebrew_completion_command_advances_in_api_flow() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    # Send Hebrew commands as JSON so the request body stays UTF-8 encoded.
    first_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert first_response.status_code == 200
    assert (
        first_response.json()["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05e7\u05de\u05d7 \u05dc\u05d1\u05df."
    )

    done_response = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert done_response.status_code == 200
    assert (
        done_response.json()["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05d7\u05dc\u05d1."
    )

    second_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert second_response.status_code == 200
    assert (
        second_response.json()["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05d7\u05dc\u05d1."
    )
    assert second_response.json()["session"]["current_item_index"] == 1


def test_all_supported_hebrew_completion_commands_advance_api_flow() -> None:
    client = TestClient(app)
    recipe_id = client.get("/recipes").json()[0]["id"]

    completion_commands = [
        "\u05e9\u05de\u05ea\u05d9",
        "\u05d4\u05d5\u05e1\u05e4\u05ea\u05d9",
        "\u05e1\u05d9\u05d9\u05de\u05ea\u05d9",
    ]

    expected_answer = "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05d7\u05dc\u05d1."

    for command in completion_commands:
        session_id = _start_session(client, recipe_id)
        client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})

        done_response = client.post(f"/session/{session_id}/ask", json={"text": command})
        assert done_response.status_code == 200
        assert done_response.json()["answer"] == expected_answer
        assert done_response.json()["session"]["current_item_index"] == 1
        assert done_response.json()["session"]["current_phase"] == "ingredients"


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

    first_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert first_done.status_code == 200
    assert (
        first_done.json()["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05d5\u05e1 \u05d7\u05dc\u05d1."
    )

    second_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert second_done.status_code == 200
    assert (
        second_done.json()["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05e3 \u05e1\u05d5\u05db\u05e8 \u05dc\u05d1\u05df."
    )

    third_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert third_done.status_code == 200
    third_payload = third_done.json()
    assert third_payload["answer"] == "Mix flour, sugar, and milk into a smooth batter."
    assert third_payload["session"]["current_phase"] == "steps"
    assert third_payload["session"]["current_item_index"] == 0

    fourth_done = client.post(f"/session/{session_id}/ask", json={"text": HE_DONE})
    assert fourth_done.status_code == 200
    fourth_payload = fourth_done.json()
    assert (
        fourth_payload["answer"]
        == "\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 1 \u05db\u05e3 \u05e9\u05de\u05df."
    )
    assert fourth_payload["session"]["current_section_index"] == 1
    assert fourth_payload["session"]["current_phase"] == "ingredients"
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
    assert reloaded_session.current_phase == "ingredients"


def test_time_left_english_response_shape() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    session_id = _start_session(client, recipe_id)

    client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    ask_response = client.post(f"/session/{session_id}/ask", json={"text": "time left"})
    assert ask_response.status_code == 200

    answer = ask_response.json()["answer"]
    assert re.search(r"^Time left: \d+ (?:seconds|minutes|hours)\.$", answer)

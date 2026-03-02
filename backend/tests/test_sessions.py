from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
from app.store import store


def setup_function() -> None:
    store.clear()
    seed_sample_recipe()


def test_session_flow_next_step() -> None:
    client = TestClient(app)

    recipes_response = client.get("/recipes")
    assert recipes_response.status_code == 200
    recipes = recipes_response.json()
    assert recipes

    recipe_id = recipes[0]["id"]

    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session = start_response.json()

    ask_now_response = client.post(
        f"/session/{session['id']}/ask",
        json={"text": "?? ?????"},
    )
    assert ask_now_response.status_code == 200
    assert "Step 1" in ask_now_response.json()["answer"]

    ask_next_response = client.post(
        f"/session/{session['id']}/ask",
        json={"text": "???"},
    )
    assert ask_next_response.status_code == 200

    payload = ask_next_response.json()
    action_types = [action["type"] for action in payload["actions"]]

    assert "NEXT_STEP" in action_types
    assert payload["session"]["current_step"] == 1

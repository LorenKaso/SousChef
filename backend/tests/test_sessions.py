from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
from app.models import Timer
from app.store import store

HE_WHAT_NOW = "מה עכשיו"
NEXT_TEXT = "next"
HE_TIME_LEFT = "כמה זמן נשאר"


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
        json={"text": HE_WHAT_NOW},
    )
    assert ask_now_response.status_code == 200
    assert "שלב 1" in ask_now_response.json()["answer"]

    ask_next_response = client.post(
        f"/session/{session['id']}/ask",
        json={"text": NEXT_TEXT},
    )
    assert ask_next_response.status_code == 200

    payload = ask_next_response.json()
    action_types = [action["type"] for action in payload["actions"]]

    assert "NEXT_STEP" in action_types
    assert payload["session"]["current_step"] == 2


def test_session_expires_after_ttl(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "1")
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    session = store.sessions[session_id]
    session.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    store.sessions[session_id] = session

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert ask_response.status_code == 404


def test_session_not_expired_if_recent(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "10")
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_WHAT_NOW})
    assert ask_response.status_code == 200


def test_expired_timers_removed() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

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
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_TIME_LEFT})
    assert ask_response.status_code == 200
    answer = ask_response.json()["answer"]
    assert re.search(r"^אין טיימר פעיל\.$", answer)


def test_time_left_active_timer() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    start_timer_response = client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    assert start_timer_response.status_code == 200

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_TIME_LEFT})
    assert ask_response.status_code == 200
    answer = ask_response.json()["answer"]
    match = re.search(
        r"^נשארו (\d+) (?:שניות|דקות|שעות)\.$",
        answer,
    )
    assert match is not None
    assert int(match.group(1)) >= 1


def test_time_left_timer_finished(monkeypatch) -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    start_timer_response = client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    assert start_timer_response.status_code == 200

    session = store.sessions[session_id]
    assert session.active_timers
    session.active_timers[-1].started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    store.sessions[session_id] = session

    monkeypatch.setattr(store, "_prune_expired_timers", lambda _session, _now: None)

    ask_response = client.post(f"/session/{session_id}/ask", json={"text": HE_TIME_LEFT})
    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert payload["answer"] == "הטיימר נגמר."
    action_types = [action["type"] for action in payload["actions"]]
    assert "TIMER_FINISHED" in action_types


def test_time_left_english_response_shape() -> None:
    client = TestClient(app)

    recipe_id = client.get("/recipes").json()[0]["id"]
    start_response = client.post("/session/start", json={"recipe_id": recipe_id})
    assert start_response.status_code == 200
    session_id = start_response.json()["id"]

    client.post(f"/session/{session_id}/ask", json={"text": "10 seconds"})
    ask_response = client.post(f"/session/{session_id}/ask", json={"text": "time left"})
    assert ask_response.status_code == 200

    answer = ask_response.json()["answer"]
    assert re.search(r"^Time left: \d+ (?:seconds|minutes|hours)\.$", answer)

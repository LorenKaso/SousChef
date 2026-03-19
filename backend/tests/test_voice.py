from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.store import store


def setup_function() -> None:
    init_db()
    store.clear()
    seed_sample_recipe()


def test_voice_session_start_creates_separate_voice_and_recipe_sessions() -> None:
    client = TestClient(app)

    response = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    payload = response.json()
    assert payload["voice_session"]["state"] == "listening"
    assert payload["voice_session"]["recipe_session_id"] == payload["recipe_session"]["id"]
    assert payload["voice_session"]["stt_model"] == "openai/whisper-large-v3-turbo"
    assert payload["voice_session"]["tts_model"] == "stub-tts"


def test_voice_turn_routes_through_existing_guided_flow_and_returns_tts_payload() -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"transcript_text": "what now"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    payload = response.json()
    assert payload["transcript"] == "what now"
    assert payload["voice_session"]["state"] == "speaking"
    assert payload["recipe_session"]["id"] == start.json()["recipe_session"]["id"]
    assert "pasta" in payload["answer"].lower()
    assert payload["audio_base64"]
    assert payload["audio_content_type"] == "text/plain; charset=utf-8"
    assert payload["audio_encoding"] == "base64"


def test_voice_turn_repairs_mojibake_transcript_text_before_processing() -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"transcript_text": "×ž×” ×¢×›×©×™×•?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert payload["voice_session"]["last_transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"


def test_voice_turn_accepts_audio_base64_when_stt_pipeline_is_available(monkeypatch) -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    captured: dict[str, object] = {}

    def fake_pipeline(audio_path: str, *, generate_kwargs: dict[str, str]):
        captured["audio_path"] = audio_path
        captured["generate_kwargs"] = generate_kwargs
        return {"text": "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"}

    monkeypatch.setattr(store.stt_service, "_pipeline", None)
    monkeypatch.setattr(store.stt_service, "_build_pipeline", lambda: fake_pipeline)

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"audio_base64": "ZmFrZQ==", "mime_type": "audio/ogg", "language_hint": "he"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert payload["voice_session"]["last_transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert payload["voice_session"]["last_answer"]
    assert payload["voice_session"]["state"] == "speaking"
    assert str(captured["audio_path"]).endswith(".ogg")
    assert captured["generate_kwargs"] == {"task": "transcribe", "language": "hebrew"}


def test_voice_turn_rejects_invalid_audio_base64() -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"audio_base64": "!!!not-base64!!!", "mime_type": "audio/ogg"},
    )

    assert response.status_code == 422
    assert "invalid audio_base64" in response.json()["detail"].lower()


def test_voice_turn_returns_503_when_stt_inference_fails(monkeypatch) -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    monkeypatch.setattr(store.stt_service, "_pipeline", None)
    monkeypatch.setattr(
        store.stt_service,
        "_build_pipeline",
        lambda: (_ for _ in ()).throw(RuntimeError("Speech model initialization failed.")),
    )

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"audio_base64": "ZmFrZQ==", "mime_type": "audio/ogg"},
    )

    assert response.status_code == 503
    assert "speech model initialization failed" in response.json()["detail"].lower()


def test_voice_session_stop_marks_session_stopped() -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    stop = client.post(f"/voice/session/{voice_session_id}/stop")

    assert stop.status_code == 200
    assert stop.json()["voice_session"]["state"] == "stopped"

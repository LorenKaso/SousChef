from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.models import DisplayLanguage
from app.services.stt_service import DEFAULT_STT_MODEL, STTService
from app.services.tts_service import DEFAULT_TTS_MODEL, TTSService
from app.store import store


_FAKE_WAV_BYTES = (
    b"RIFF\x24\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
    b"data\x00\x00\x00\x00"
)
_FAKE_WAV_BASE64 = base64.b64encode(_FAKE_WAV_BYTES).decode("ascii")


class _FakeNoGrad:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeTorch:
    float16 = "float16"
    float32 = "float32"

    class cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    @staticmethod
    def no_grad() -> _FakeNoGrad:
        return _FakeNoGrad()


class _FakeModel:
    def __init__(self, sample_rate: int) -> None:
        self.config = type("Config", (), {"sampling_rate": sample_rate})()
        self.device = None

    def to(self, device: str) -> None:
        self.device = device

    def __call__(self, **kwargs):
        _ = kwargs
        return type("Output", (), {"waveform": [[0.0, 0.25, -0.25, 0.0]]})()


class _FakeTTSResult:
    def __init__(self, provider_model: str) -> None:
        self.audio_base64 = _FAKE_WAV_BASE64
        self.content_type = "audio/wav"
        self.encoding = "base64"
        self.provider_model = provider_model



def _mock_tts(monkeypatch, provider_model: str = "facebook/mms-tts-eng") -> None:
    monkeypatch.setattr(
        store.tts_service,
        "synthesize",
        lambda *, text, language=None: _FakeTTSResult(provider_model),
    )



def setup_function() -> None:
    init_db()
    store.clear()
    seed_sample_recipe()



def test_tts_service_uses_default_local_hugging_face_models() -> None:
    service = TTSService()

    assert service.hebrew_model_name == "facebook/mms-tts-heb"
    assert service.english_model_name == "facebook/mms-tts-eng"
    assert service.model_name == DEFAULT_TTS_MODEL



def test_tts_service_synthesizes_hebrew_wav_with_mocked_local_model() -> None:
    tokenizer_calls: list[str] = []
    model_calls: list[str] = []

    def fake_tokenizer_loader(model_name: str):
        tokenizer_calls.append(model_name)

        def fake_tokenizer(text: str, return_tensors: str):
            assert return_tensors == "pt"
            return {"text": text}

        return fake_tokenizer

    def fake_model_loader(model_name: str):
        model_calls.append(model_name)
        return _FakeModel(sample_rate=16000)

    service = TTSService(
        torch_module=_FakeTorch(),
        tokenizer_loader=fake_tokenizer_loader,
        model_loader=fake_model_loader,
    )

    result = service.synthesize(text="\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?", language=DisplayLanguage.HE)

    assert result.provider_model == "facebook/mms-tts-heb"
    assert result.content_type == "audio/wav"
    assert result.encoding == "base64"
    assert base64.b64decode(result.audio_base64).startswith(b"RIFF")
    assert tokenizer_calls == ["facebook/mms-tts-heb"]
    assert model_calls == ["facebook/mms-tts-heb"]



def test_tts_service_uses_english_model_and_caches_loaded_pipeline() -> None:
    model_calls: list[str] = []

    def fake_tokenizer_loader(model_name: str):
        def fake_tokenizer(text: str, return_tensors: str):
            _ = text
            _ = return_tensors
            return {"model_name": model_name}

        return fake_tokenizer

    def fake_model_loader(model_name: str):
        model_calls.append(model_name)
        return _FakeModel(sample_rate=22050)

    service = TTSService(
        torch_module=_FakeTorch(),
        tokenizer_loader=fake_tokenizer_loader,
        model_loader=fake_model_loader,
    )

    first = service.synthesize(text="what now", language=DisplayLanguage.EN)
    second = service.synthesize(text="next step", language=DisplayLanguage.EN)

    assert first.provider_model == "facebook/mms-tts-eng"
    assert second.provider_model == "facebook/mms-tts-eng"
    assert model_calls == ["facebook/mms-tts-eng"]



def test_tts_service_rejects_empty_text() -> None:
    service = TTSService()

    try:
        service.synthesize(text="   ", language=DisplayLanguage.EN)
    except RuntimeError as exc:
        assert "empty text" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("Expected RuntimeError for empty TTS text.")



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
    assert payload["voice_session"]["stt_model"] == DEFAULT_STT_MODEL
    assert payload["voice_session"]["tts_model"] == "facebook/mms-tts-heb|facebook/mms-tts-eng"



def test_voice_turn_routes_through_existing_guided_flow_and_returns_tts_payload(monkeypatch) -> None:
    client = TestClient(app)
    _mock_tts(monkeypatch, provider_model="facebook/mms-tts-eng")
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
    assert payload["voice_session"]["tts_model"] == "facebook/mms-tts-eng"
    assert payload["recipe_session"]["id"] == start.json()["recipe_session"]["id"]
    assert "pasta" in payload["answer"].lower()
    assert payload["audio_base64"]
    assert base64.b64decode(payload["audio_base64"]).startswith(b"RIFF")
    assert payload["audio_content_type"] == "audio/wav"
    assert payload["audio_encoding"] == "base64"



def test_voice_turn_repairs_mojibake_transcript_text_before_processing(monkeypatch) -> None:
    client = TestClient(app)
    _mock_tts(monkeypatch, provider_model="facebook/mms-tts-heb")
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"transcript_text": "מה עכשיו?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert payload["voice_session"]["last_transcript"] == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert payload["voice_session"]["tts_model"] == "facebook/mms-tts-heb"



def test_voice_turn_accepts_audio_base64_when_stt_pipeline_is_available(monkeypatch) -> None:
    client = TestClient(app)
    _mock_tts(monkeypatch, provider_model="facebook/mms-tts-heb")
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
    assert payload["voice_session"]["tts_model"] == "facebook/mms-tts-heb"
    assert payload["audio_content_type"] == "audio/wav"
    assert str(captured["audio_path"]).endswith(".ogg")
    assert captured["generate_kwargs"] == {"task": "transcribe", "language": "hebrew"}



def test_stt_transcript_text_shortcut_returns_repaired_text() -> None:
    service = STTService()

    result = service.transcribe(
        transcript_text="\u00d7\u009e\u00d7\u0094 \u00d7\u00a2\u00d7\u009b\u00d7\u00a9\u00d7\u0099\u00d7\u0095?",
        language_hint=DisplayLanguage.HE,
    )

    assert result.text == "\u05de\u05d4 \u05e2\u05db\u05e9\u05d9\u05d5?"
    assert result.provider_model == DEFAULT_STT_MODEL
    assert result.language == "he"



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



def test_stt_invalid_audio_base64_raises_value_error() -> None:
    service = STTService()

    try:
        service.transcribe(audio_base64="!!!not-base64!!!", mime_type="audio/ogg")
    except ValueError as exc:
        assert "invalid audio_base64" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for invalid audio_base64.")



def test_voice_turn_returns_503_when_stt_inference_fails(monkeypatch) -> None:
    client = TestClient(app)
    _mock_tts(monkeypatch)
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



def test_voice_turn_returns_503_when_tts_synthesis_fails(monkeypatch) -> None:
    client = TestClient(app)
    start = client.post(
        "/voice/session/start",
        json={"recipe_id": "recipe-mushroom-cream-pasta"},
    )
    voice_session_id = start.json()["voice_session"]["id"]

    monkeypatch.setattr(
        store.tts_service,
        "synthesize",
        lambda *, text, language=None: (_ for _ in ()).throw(RuntimeError("TTS synthesis failed for model 'facebook/mms-tts-eng'.")),
    )

    response = client.post(
        f"/voice/session/{voice_session_id}/turn",
        json={"transcript_text": "what now"},
    )

    assert response.status_code == 503
    assert "tts synthesis failed" in response.json()["detail"].lower()



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

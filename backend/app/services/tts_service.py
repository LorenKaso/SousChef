from __future__ import annotations

import base64

from pydantic import BaseModel

from ..models import DisplayLanguage


DEFAULT_TTS_MODEL = "stub-tts"


class SynthesisResult(BaseModel):
    audio_base64: str
    content_type: str
    encoding: str
    provider_model: str


class TTSService:
    def __init__(self, *, model_name: str = DEFAULT_TTS_MODEL) -> None:
        self.model_name = model_name

    def synthesize(
        self,
        *,
        text: str,
        language: DisplayLanguage | None = None,
    ) -> SynthesisResult:
        _ = language
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return SynthesisResult(
            audio_base64=payload,
            content_type="text/plain; charset=utf-8",
            encoding="base64",
            provider_model=self.model_name,
        )

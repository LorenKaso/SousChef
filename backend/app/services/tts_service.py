from __future__ import annotations

import base64
import io
import wave
from typing import Any

import numpy as np
from pydantic import BaseModel

from ..models import DisplayLanguage


DEFAULT_HE_TTS_MODEL = "facebook/mms-tts-heb"
DEFAULT_EN_TTS_MODEL = "facebook/mms-tts-eng"
DEFAULT_TTS_MODEL = f"{DEFAULT_HE_TTS_MODEL}|{DEFAULT_EN_TTS_MODEL}"
_MAX_TTS_TEXT_CHARS = 500


class SynthesisResult(BaseModel):
    audio_base64: str
    content_type: str
    encoding: str
    provider_model: str


class TTSService:
    def __init__(
        self,
        *,
        hebrew_model_name: str = DEFAULT_HE_TTS_MODEL,
        english_model_name: str = DEFAULT_EN_TTS_MODEL,
        torch_module: Any | None = None,
        model_loader: Any | None = None,
        tokenizer_loader: Any | None = None,
    ) -> None:
        self.hebrew_model_name = hebrew_model_name
        self.english_model_name = english_model_name
        self.model_name = DEFAULT_TTS_MODEL
        self._torch_module = torch_module
        self._model_loader = model_loader
        self._tokenizer_loader = tokenizer_loader
        self._pipelines: dict[DisplayLanguage, tuple[Any, Any]] = {}
        self._device: str | None = None

    def synthesize(
        self,
        *,
        text: str,
        language: DisplayLanguage | None = None,
    ) -> SynthesisResult:
        normalized_text = _normalize_text(text)
        selected_language = language or _detect_tts_language(normalized_text)
        tokenizer, model = self._get_pipeline(selected_language)
        model_name = self._model_name_for_language(selected_language)
        torch = self._get_torch()

        try:
            inputs = tokenizer(normalized_text, return_tensors="pt")
            if hasattr(inputs, "to"):
                inputs = inputs.to(self._device)
            with torch.no_grad():
                waveform = model(**inputs).waveform
            audio = _waveform_to_numpy(waveform)
            sample_rate = int(getattr(model.config, "sampling_rate", 16000))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"TTS synthesis failed for model '{model_name}'.") from exc

        wav_bytes = _encode_wav(audio, sample_rate)
        return SynthesisResult(
            audio_base64=base64.b64encode(wav_bytes).decode("ascii"),
            content_type="audio/wav",
            encoding="base64",
            provider_model=model_name,
        )

    def _get_pipeline(self, language: DisplayLanguage) -> tuple[Any, Any]:
        if language not in self._pipelines:
            tokenizer_loader, model_loader = self._get_transformer_loaders()
            model_name = self._model_name_for_language(language)
            tokenizer = tokenizer_loader(model_name)
            model = model_loader(model_name)
            if hasattr(model, "to"):
                model.to(self._get_device())
            self._pipelines[language] = (tokenizer, model)
        return self._pipelines[language]

    def _get_torch(self):
        if self._torch_module is None:
            try:
                import torch as imported_torch
            except ImportError as exc:
                raise RuntimeError("PyTorch is required for local TTS.") from exc
            self._torch_module = imported_torch
        return self._torch_module

    def _get_transformer_loaders(self) -> tuple[Any, Any]:
        if self._tokenizer_loader is None or self._model_loader is None:
            try:
                from transformers import AutoTokenizer, VitsModel
            except ImportError as exc:
                raise RuntimeError("transformers is required for local TTS.") from exc
            self._tokenizer_loader = self._tokenizer_loader or AutoTokenizer.from_pretrained
            self._model_loader = self._model_loader or VitsModel.from_pretrained
        return self._tokenizer_loader, self._model_loader

    def _get_device(self) -> str:
        if self._device is None:
            torch = self._get_torch()
            self._device = "cuda" if bool(torch.cuda.is_available()) else "cpu"
        return self._device

    def _model_name_for_language(self, language: DisplayLanguage) -> str:
        return self.hebrew_model_name if language == DisplayLanguage.HE else self.english_model_name



def _normalize_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise RuntimeError("TTS received empty text.")
    if len(normalized) > _MAX_TTS_TEXT_CHARS:
        normalized = normalized[:_MAX_TTS_TEXT_CHARS].rstrip()
    return normalized



def _waveform_to_numpy(waveform: Any) -> np.ndarray:
    array = waveform.detach().cpu().numpy() if hasattr(waveform, "detach") else np.asarray(waveform)
    array = np.asarray(array, dtype=np.float32).squeeze()
    if array.ndim == 0:
        return np.asarray([float(array)], dtype=np.float32)
    return array



def _encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buffer.getvalue()



def _detect_tts_language(text: str) -> DisplayLanguage:
    if any("\u0590" <= char <= "\u05FF" for char in text):
        return DisplayLanguage.HE
    return DisplayLanguage.EN

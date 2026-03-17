from __future__ import annotations

import base64
import binascii
import os
import tempfile

from pydantic import BaseModel

from ..models import DisplayLanguage


DEFAULT_STT_MODEL = "openai/whisper-large-v3-turbo"
_DEFAULT_GENERATE_KWARGS = {
    "task": "transcribe",
}
_LANGUAGE_HINTS = {
    DisplayLanguage.EN: "english",
    DisplayLanguage.HE: "hebrew",
}


class TranscriptionResult(BaseModel):
    text: str
    provider_model: str
    language: str | None = None


class STTService:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_STT_MODEL,
        torch_module=None,
        model_loader=None,
        processor_loader=None,
        pipeline_factory=None,
    ) -> None:
        self.model_name = model_name
        self._torch_module = torch_module
        self._model_loader = model_loader
        self._processor_loader = processor_loader
        self._pipeline_factory = pipeline_factory
        self._pipeline = None

    def transcribe(
        self,
        *,
        audio_base64: str | None = None,
        transcript_text: str | None = None,
        mime_type: str | None = None,
        language_hint: DisplayLanguage | None = None,
    ) -> TranscriptionResult:
        if transcript_text is not None and transcript_text.strip():
            return TranscriptionResult(
                text=transcript_text.strip(),
                provider_model=self.model_name,
                language=language_hint.value if language_hint is not None else None,
            )
        if audio_base64:
            audio_bytes = self._decode_audio_base64(audio_base64)
            return self._transcribe_audio_bytes(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                language_hint=language_hint,
            )
        raise ValueError("Either transcript_text or audio_base64 is required.")

    def _transcribe_audio_bytes(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: DisplayLanguage | None,
    ) -> TranscriptionResult:
        suffix = _suffix_for_mime_type(mime_type)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            result = self._run_pipeline(temp_path, language_hint=language_hint)
            if not isinstance(result, dict):
                raise RuntimeError("Speech transcription returned an unexpected result type.")

            text = str(result.get("text", "")).strip()
            if not text:
                raise ValueError("Transcription returned empty text.")

            return TranscriptionResult(
                text=text,
                provider_model=self.model_name,
                language=language_hint.value if language_hint is not None else None,
            )
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Audio transcription failed.") from exc
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _run_pipeline(self, audio_path: str, *, language_hint: DisplayLanguage | None):
        pipeline = self._get_pipeline()
        generate_kwargs = dict(_DEFAULT_GENERATE_KWARGS)
        if language_hint is not None:
            generate_kwargs["language"] = _LANGUAGE_HINTS.get(language_hint, language_hint.value)
        return pipeline(audio_path, generate_kwargs=generate_kwargs)

    def _get_pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()
        return self._pipeline

    def _build_pipeline(self):
        torch = self._torch_module
        if torch is None:
            try:
                import torch as imported_torch
            except ImportError as exc:
                raise RuntimeError(
                    "PyTorch is required for speech transcription."
                ) from exc
            torch = imported_torch

        model_loader = self._model_loader
        processor_loader = self._processor_loader
        pipeline_factory = self._pipeline_factory
        if model_loader is None or processor_loader is None or pipeline_factory is None:
            try:
                from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
            except ImportError as exc:
                raise RuntimeError(
                    "transformers is required for speech transcription."
                ) from exc
            model_loader = model_loader or AutoModelForSpeechSeq2Seq.from_pretrained
            processor_loader = processor_loader or AutoProcessor.from_pretrained
            pipeline_factory = pipeline_factory or pipeline

        use_cuda = bool(torch.cuda.is_available())
        torch_dtype = torch.float16 if use_cuda else torch.float32
        device_index = 0 if use_cuda else -1
        device_label = "cuda:0" if use_cuda else "cpu"

        model = model_loader(
            self.model_name,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        if hasattr(model, "to"):
            model.to(device_label)

        processor = processor_loader(self.model_name)
        return pipeline_factory(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            chunk_length_s=30,
            batch_size=8,
            max_new_tokens=128,
            torch_dtype=torch_dtype,
            device=device_index,
        )

    @staticmethod
    def _decode_audio_base64(audio_base64: str) -> bytes:
        try:
            decoded = base64.b64decode(audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid audio_base64 payload.") from exc
        if not decoded:
            raise ValueError("Audio payload is empty.")
        return decoded


def _suffix_for_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    normalized = mime_type.lower().strip()
    if "ogg" in normalized:
        return ".ogg"
    if "wav" in normalized:
        return ".wav"
    if "mpeg" in normalized or "mp3" in normalized:
        return ".mp3"
    if "webm" in normalized:
        return ".webm"
    if "mp4" in normalized or "m4a" in normalized:
        return ".m4a"
    return ".bin"

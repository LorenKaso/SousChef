from __future__ import annotations

from fastapi import HTTPException

from ..models import (
    DisplayLanguage,
    VoiceSession,
    VoiceSessionStartResponse,
    VoiceSessionState,
    VoiceSessionStopResponse,
    VoiceSessionTurnRequest,
    VoiceSessionTurnResponse,
)
from ..text_utils import repair_text_if_mojibake
from .orchestrator import process_ask
from .rag_service import RagService
from .recipe_service import RecipeService
from .session_service import SessionService
from .stt_service import STTService
from .tts_service import TTSService
from .voice_session_service import VoiceSessionService


class VoiceOrchestrator:
    def __init__(
        self,
        *,
        recipe_service: RecipeService,
        session_service: SessionService,
        voice_session_service: VoiceSessionService,
        rag_service: RagService,
        stt_service: STTService,
        tts_service: TTSService,
    ) -> None:
        self.recipe_service = recipe_service
        self.session_service = session_service
        self.voice_session_service = voice_session_service
        self.rag_service = rag_service
        self.stt_service = stt_service
        self.tts_service = tts_service

    def start_voice_session(self, *, recipe_id: str) -> VoiceSessionStartResponse:
        recipe = self.recipe_service.get_recipe(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Recipe not found")

        recipe_session = self.session_service.start_session(recipe_id)
        voice_session = self.voice_session_service.start_session(
            recipe_session_id=recipe_session.id,
            stt_model=self.stt_service.model_name,
            tts_model=self.tts_service.model_name,
        )
        return VoiceSessionStartResponse(
            voice_session=voice_session,
            recipe_session=recipe_session,
        )

    def process_turn(
        self,
        *,
        voice_session_id: str,
        payload: VoiceSessionTurnRequest,
    ) -> VoiceSessionTurnResponse:
        voice_session = self._get_voice_session(voice_session_id)
        if voice_session.state == VoiceSessionState.STOPPED:
            raise HTTPException(status_code=409, detail="Voice session has already been stopped")

        recipe_session = self.session_service.get_session(voice_session.recipe_session_id)
        if recipe_session is None:
            raise HTTPException(status_code=404, detail="Recipe session not found")

        recipe = self.recipe_service.get_recipe(recipe_session.recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Recipe not found")

        voice_session.state = VoiceSessionState.PROCESSING
        self.voice_session_service.update_session(voice_session)

        try:
            transcription = self.stt_service.transcribe(
                audio_base64=payload.audio_base64,
                transcript_text=payload.transcript_text,
                mime_type=payload.mime_type,
                language_hint=payload.language_hint,
            )
        except ValueError as exc:
            voice_session.state = VoiceSessionState.LISTENING
            self.voice_session_service.update_session(voice_session)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            voice_session.state = VoiceSessionState.LISTENING
            self.voice_session_service.update_session(voice_session)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        normalized_transcript = repair_text_if_mojibake(transcription.text)
        answer_text, actions, updated_recipe_session = process_ask(
            recipe_session,
            recipe,
            normalized_transcript,
            rag_service=self.rag_service,
        )
        answer_text = repair_text_if_mojibake(answer_text)
        updated_recipe_session = self.session_service.update_session(updated_recipe_session)

        language = payload.language_hint or _detect_answer_language(answer_text)
        synthesized = self.tts_service.synthesize(text=answer_text, language=language)

        voice_session.state = VoiceSessionState.SPEAKING
        voice_session.last_transcript = normalized_transcript
        voice_session.last_answer = answer_text
        updated_voice_session = self.voice_session_service.update_session(voice_session)

        return VoiceSessionTurnResponse(
            transcript=normalized_transcript,
            answer=answer_text,
            actions=actions,
            voice_session=updated_voice_session,
            recipe_session=updated_recipe_session,
            audio_base64=synthesized.audio_base64,
            audio_content_type=synthesized.content_type,
            audio_encoding=synthesized.encoding,
        )

    def stop_voice_session(self, *, voice_session_id: str) -> VoiceSessionStopResponse:
        voice_session = self.voice_session_service.stop_session(voice_session_id)
        if voice_session is None:
            raise HTTPException(status_code=404, detail="Voice session not found")
        return VoiceSessionStopResponse(voice_session=voice_session)

    def _get_voice_session(self, voice_session_id: str) -> VoiceSession:
        voice_session = self.voice_session_service.get_session(voice_session_id)
        if voice_session is None:
            raise HTTPException(status_code=404, detail="Voice session not found")
        return voice_session


def _detect_answer_language(text: str) -> DisplayLanguage:
    if any("\u0590" <= char <= "\u05FF" for char in text):
        return DisplayLanguage.HE
    return DisplayLanguage.EN

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..models import VoiceSession, VoiceSessionState
from ..repositories.voice_session_repository import VoiceSessionRepository


class VoiceSessionService:
    def __init__(self, repository: VoiceSessionRepository | None = None) -> None:
        self.repository = repository or VoiceSessionRepository()

    def start_session(
        self,
        *,
        recipe_session_id: str,
        stt_model: str | None = None,
        tts_model: str | None = None,
    ) -> VoiceSession:
        now = datetime.now(timezone.utc)
        voice_session = VoiceSession(
            id=str(uuid.uuid4()),
            recipe_session_id=recipe_session_id,
            state=VoiceSessionState.LISTENING,
            stt_model=stt_model,
            tts_model=tts_model,
            created_at=now,
            updated_at=now,
        )
        return self.repository.add(voice_session)

    def get_session(self, voice_session_id: str) -> VoiceSession | None:
        return self.repository.get(voice_session_id)

    def update_session(self, voice_session: VoiceSession) -> VoiceSession:
        voice_session.updated_at = datetime.now(timezone.utc)
        return self.repository.upsert(voice_session)

    def stop_session(self, voice_session_id: str) -> VoiceSession | None:
        voice_session = self.repository.get(voice_session_id)
        if voice_session is None:
            return None
        voice_session.state = VoiceSessionState.STOPPED
        voice_session.updated_at = datetime.now(timezone.utc)
        return self.repository.upsert(voice_session)

    def clear(self) -> None:
        self.repository.clear()

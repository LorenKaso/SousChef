from __future__ import annotations

from datetime import datetime

from ..db import get_connection
from ..models import VoiceSession, VoiceSessionState


class VoiceSessionRepository:
    def add(self, voice_session: VoiceSession) -> VoiceSession:
        return self.upsert(voice_session)

    def upsert(self, voice_session: VoiceSession) -> VoiceSession:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO voice_sessions (
                    id,
                    recipe_session_id,
                    state,
                    last_transcript,
                    last_answer,
                    stt_model,
                    tts_model,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    voice_session.id,
                    voice_session.recipe_session_id,
                    voice_session.state.value,
                    voice_session.last_transcript,
                    voice_session.last_answer,
                    voice_session.stt_model,
                    voice_session.tts_model,
                    voice_session.created_at.isoformat(),
                    voice_session.updated_at.isoformat(),
                ),
            )
        return voice_session

    def get(self, voice_session_id: str) -> VoiceSession | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    recipe_session_id,
                    state,
                    last_transcript,
                    last_answer,
                    stt_model,
                    tts_model,
                    created_at,
                    updated_at
                FROM voice_sessions
                WHERE id = ?
                """,
                (voice_session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate(row)

    def list(self) -> list[VoiceSession]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    recipe_session_id,
                    state,
                    last_transcript,
                    last_answer,
                    stt_model,
                    tts_model,
                    created_at,
                    updated_at
                FROM voice_sessions
                ORDER BY created_at
                """
            ).fetchall()
            return [self._hydrate(row) for row in rows]

    def delete(self, voice_session_id: str) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM voice_sessions WHERE id = ?", (voice_session_id,))

    def clear(self) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM voice_sessions")

    @staticmethod
    def _hydrate(row) -> VoiceSession:
        return VoiceSession(
            id=row["id"],
            recipe_session_id=row["recipe_session_id"],
            state=VoiceSessionState(row["state"]),
            last_transcript=row["last_transcript"],
            last_answer=row["last_answer"],
            stt_model=row["stt_model"],
            tts_model=row["tts_model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

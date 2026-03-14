from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from ..models import Session
from ..repositories.session_repository import SessionRepository


class SessionService:
    def __init__(self, repository: SessionRepository | None = None) -> None:
        self.repository = repository or SessionRepository()

    def start_session(self, recipe_id: str) -> Session:
        now = datetime.now(timezone.utc)
        session = Session(
            id=str(uuid.uuid4()),
            recipe_id=recipe_id,
            created_at=now,
            updated_at=now,
        )
        self._prune_expired_timers(session, now)
        return self.repository.add(session)

    def create_session(self, session: Session) -> Session:
        now = datetime.now(timezone.utc)
        session.created_at = now
        session.updated_at = now
        self._prune_expired_timers(session, now)
        return self.repository.add(session)

    def get_session(self, session_id: str) -> Session | None:
        session = self.repository.get(session_id)
        if session is None:
            return None

        now = datetime.now(timezone.utc)
        if self._is_session_expired(session, now):
            self.repository.delete(session_id)
            return None

        self._prune_expired_timers(session, now)
        self.repository.upsert(session)
        return session

    def update_session(self, session: Session) -> Session:
        now = datetime.now(timezone.utc)
        session.updated_at = now
        self._prune_expired_timers(session, now)
        return self.repository.upsert(session)

    def delete_session(self, session_id: str) -> None:
        self.repository.delete(session_id)

    def list_sessions(self) -> list[Session]:
        return self.repository.list()

    def clear(self) -> None:
        self.repository.clear()

    @staticmethod
    def _session_ttl_seconds() -> int:
        raw = os.getenv("SESSION_TTL_SECONDS", "86400")
        try:
            ttl = int(raw)
        except (TypeError, ValueError):
            return 86400
        return ttl if ttl > 0 else 86400

    def _is_session_expired(self, session: Session, now: datetime) -> bool:
        age_seconds = (now - self._normalize_datetime(session.updated_at)).total_seconds()
        return age_seconds > self._session_ttl_seconds()

    def _prune_expired_timers(self, session: Session, now: datetime) -> None:
        active_timers = []
        for timer in session.active_timers:
            started_at = self._normalize_datetime(timer.started_at)
            expires_at = started_at + timedelta(seconds=timer.seconds)
            if now <= expires_at:
                timer.started_at = started_at
                active_timers.append(timer)
        session.active_timers = active_timers

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

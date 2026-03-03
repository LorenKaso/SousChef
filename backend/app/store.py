from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from .models import Recipe, Session


class InMemoryStore:
    def __init__(self) -> None:
        self.recipes: dict[str, Recipe] = {}
        self.sessions: dict[str, Session] = {}

    def is_empty(self) -> bool:
        return len(self.recipes) == 0

    def clear(self) -> None:
        self.recipes.clear()
        self.sessions.clear()

    def add_recipe(self, recipe: Recipe) -> Recipe:
        self.recipes[recipe.id] = recipe
        return recipe

    def list_recipes(self) -> Iterable[Recipe]:
        return self.recipes.values()

    def get_recipe(self, recipe_id: str) -> Recipe | None:
        return self.recipes.get(recipe_id)

    def add_session(self, session: Session) -> Session:
        now = datetime.now(timezone.utc)
        session.created_at = now
        session.updated_at = now
        self._prune_expired_timers(session, now)
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None

        now = datetime.now(timezone.utc)
        if self._is_session_expired(session, now):
            del self.sessions[session_id]
            return None

        self._prune_expired_timers(session, now)
        return session

    def update_session(self, session: Session) -> Session:
        now = datetime.now(timezone.utc)
        session.updated_at = now
        self._prune_expired_timers(session, now)
        self.sessions[session.id] = session
        return session

    @staticmethod
    def _session_ttl_seconds() -> int:
        raw = os.getenv("SESSION_TTL_SECONDS", "86400")
        try:
            ttl = int(raw)
        except (TypeError, ValueError):
            return 86400
        return ttl if ttl > 0 else 86400

    def _is_session_expired(self, session: Session, now: datetime) -> bool:
        age_seconds = (now - session.updated_at).total_seconds()
        return age_seconds > self._session_ttl_seconds()

    @staticmethod
    def _prune_expired_timers(session: Session, now: datetime) -> None:
        active_timers = []
        for timer in session.active_timers:
            started_at = timer.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            else:
                started_at = started_at.astimezone(timezone.utc)

            expires_at = started_at + timedelta(seconds=timer.seconds)
            if now <= expires_at:
                active_timers.append(timer)

        session.active_timers = active_timers


store = InMemoryStore()

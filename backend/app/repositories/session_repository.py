from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..db import get_connection
from ..models import PendingTimerProposal, Session, Timer


class SessionRepository:
    def add(self, session: Session) -> Session:
        return self.upsert(session)

    def upsert(self, session: Session) -> Session:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO sessions (
                    id,
                    recipe_id,
                    current_section_index,
                    current_phase,
                    current_item_index,
                    pending_timer_json,
                    preferences_json,
                    metadata_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    session.id,
                    session.recipe_id,
                    session.current_section_index,
                    session.current_phase,
                    session.current_item_index,
                    self._dump_pending_timer(session.pending_timer),
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
            connection.execute("DELETE FROM timers WHERE session_id = ?", (session.id,))
            for timer in session.active_timers:
                connection.execute(
                    """
                    INSERT INTO timers (
                        id, session_id, seconds, label, step_index, started_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        timer.id,
                        session.id,
                        timer.seconds,
                        timer.label,
                        timer.step_index,
                        timer.started_at.isoformat(),
                    ),
                )
        return session

    def get(self, session_id: str) -> Session | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    recipe_id,
                    current_section_index,
                    current_phase,
                    current_item_index,
                    pending_timer_json,
                    created_at,
                    updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_session(connection, row)

    def list(self) -> list[Session]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    recipe_id,
                    current_section_index,
                    current_phase,
                    current_item_index,
                    pending_timer_json,
                    created_at,
                    updated_at
                FROM sessions
                ORDER BY created_at
                """
            ).fetchall()
            return [self._hydrate_session(connection, row) for row in rows]

    def delete(self, session_id: str) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def clear(self) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM sessions")

    @staticmethod
    def _dump_pending_timer(pending_timer: PendingTimerProposal | None) -> str | None:
        if pending_timer is None:
            return None
        return pending_timer.model_dump_json()

    def _hydrate_session(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Session:
        timer_rows = connection.execute(
            """
            SELECT id, seconds, label, step_index, started_at
            FROM timers
            WHERE session_id = ?
            ORDER BY started_at
            """,
            (row["id"],),
        ).fetchall()

        pending_timer = None
        if row["pending_timer_json"]:
            pending_timer = PendingTimerProposal.model_validate(json.loads(row["pending_timer_json"]))

        return Session(
            id=row["id"],
            recipe_id=row["recipe_id"],
            current_section_index=row["current_section_index"],
            current_phase=row["current_phase"],
            current_item_index=row["current_item_index"],
            pending_timer=pending_timer,
            active_timers=[
                Timer(
                    id=timer_row["id"],
                    seconds=timer_row["seconds"],
                    label=timer_row["label"],
                    step_index=timer_row["step_index"],
                    started_at=self._parse_datetime(timer_row["started_at"]),
                )
                for timer_row in timer_rows
            ],
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

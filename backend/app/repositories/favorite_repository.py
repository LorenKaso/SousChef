from __future__ import annotations

from datetime import datetime, timezone

from ..db import get_connection


class FavoriteRepository:
    def add(self, recipe_id: str) -> str:
        """Insert a favorite row. Returns the favorited_at ISO string."""
        favorited_at = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO favorites (recipe_id, favorited_at) VALUES (?, ?)",
                (recipe_id, favorited_at),
            )
        return favorited_at

    def remove(self, recipe_id: str) -> bool:
        """Delete a favorite row. Returns True if a row was deleted, False if none existed."""
        with get_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM favorites WHERE recipe_id = ?",
                (recipe_id,),
            )
            return cursor.rowcount > 0

    def exists(self, recipe_id: str) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM favorites WHERE recipe_id = ?",
                (recipe_id,),
            ).fetchone()
            return row is not None

    def list_ids(self) -> list[str]:
        """Return recipe_ids for all favorites, ordered newest first."""
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT recipe_id FROM favorites ORDER BY favorited_at DESC",
            ).fetchall()
            return [row["recipe_id"] for row in rows]

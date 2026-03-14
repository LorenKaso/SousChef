from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_FILENAME = "souschef.db"


def get_db_path() -> Path:
    configured = os.getenv("SOUSCHEF_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parent / "data" / DEFAULT_DB_FILENAME).resolve()


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                servings INTEGER NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS recipe_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id TEXT NOT NULL,
                section_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                metadata_json TEXT,
                UNIQUE(recipe_id, section_index),
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id TEXT NOT NULL,
                section_id INTEGER NOT NULL,
                ingredient_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                unit TEXT NOT NULL,
                metadata_json TEXT,
                UNIQUE(section_id, ingredient_index),
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY(section_id) REFERENCES recipe_sections(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id TEXT NOT NULL,
                section_id INTEGER NOT NULL,
                step_index_in_section INTEGER NOT NULL,
                global_step_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                default_timer_seconds INTEGER,
                metadata_json TEXT,
                UNIQUE(section_id, step_index_in_section),
                UNIQUE(recipe_id, global_step_index),
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY(section_id) REFERENCES recipe_sections(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                recipe_id TEXT NOT NULL,
                current_section_index INTEGER NOT NULL,
                current_phase TEXT NOT NULL,
                current_item_index INTEGER NOT NULL,
                pending_timer_json TEXT,
                preferences_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS timers (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                seconds INTEGER NOT NULL,
                label TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                metadata_json TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_recipe_sections_recipe
            ON recipe_sections(recipe_id, section_index);

            CREATE INDEX IF NOT EXISTS idx_ingredients_section
            ON ingredients(section_id, ingredient_index);

            CREATE INDEX IF NOT EXISTS idx_steps_section
            ON steps(section_id, step_index_in_section);

            CREATE INDEX IF NOT EXISTS idx_sessions_recipe
            ON sessions(recipe_id);

            CREATE INDEX IF NOT EXISTS idx_timers_session
            ON timers(session_id, started_at);
            """
        )

from __future__ import annotations

import sqlite3

from ..db import get_connection
from ..models import Ingredient, Recipe, RecipeSection, Step


class RecipeRepository:
    def add(self, recipe: Recipe) -> Recipe:
        with get_connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO recipes (id, title, servings, metadata_json) VALUES (?, ?, ?, NULL)",
                (recipe.id, recipe.title, recipe.servings),
            )
            connection.execute("DELETE FROM recipe_sections WHERE recipe_id = ?", (recipe.id,))

            for section_index, section in enumerate(recipe.sections):
                cursor = connection.execute(
                    """
                    INSERT INTO recipe_sections (recipe_id, section_index, name, metadata_json)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (recipe.id, section_index, section.name),
                )
                section_id = cursor.lastrowid
                self._insert_section_contents(connection, recipe.id, section_id, section)

        return recipe

    def list(self) -> list[Recipe]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT id, title, servings FROM recipes ORDER BY id"
            ).fetchall()
            return [self._hydrate_recipe(connection, row["id"], row) for row in rows]

    def get(self, recipe_id: str) -> Recipe | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT id, title, servings FROM recipes WHERE id = ?",
                (recipe_id,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate_recipe(connection, recipe_id, row)

    def exists_any(self) -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT 1 FROM recipes LIMIT 1").fetchone()
            return row is not None

    def clear(self) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM recipes")

    @staticmethod
    def _insert_section_contents(
        connection: sqlite3.Connection,
        recipe_id: str,
        section_id: int,
        section: RecipeSection,
    ) -> None:
        for ingredient_index, ingredient in enumerate(section.ingredients):
            connection.execute(
                """
                INSERT INTO ingredients (
                    recipe_id, section_id, ingredient_index, name, amount, unit, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    recipe_id,
                    section_id,
                    ingredient_index,
                    ingredient.name,
                    ingredient.amount,
                    ingredient.unit,
                ),
            )

        for step_index, step in enumerate(section.steps):
            connection.execute(
                """
                INSERT INTO steps (
                    recipe_id,
                    section_id,
                    step_index_in_section,
                    global_step_index,
                    text,
                    default_timer_seconds,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    recipe_id,
                    section_id,
                    step_index,
                    step.index,
                    step.text,
                    step.default_timer_seconds,
                ),
            )

    def _hydrate_recipe(
        self,
        connection: sqlite3.Connection,
        recipe_id: str,
        recipe_row: sqlite3.Row,
    ) -> Recipe:
        section_rows = connection.execute(
            """
            SELECT id, name, section_index
            FROM recipe_sections
            WHERE recipe_id = ?
            ORDER BY section_index
            """,
            (recipe_id,),
        ).fetchall()

        sections: list[RecipeSection] = []
        for section_row in section_rows:
            ingredient_rows = connection.execute(
                """
                SELECT name, amount, unit
                FROM ingredients
                WHERE section_id = ?
                ORDER BY ingredient_index
                """,
                (section_row["id"],),
            ).fetchall()
            step_rows = connection.execute(
                """
                SELECT global_step_index, text, default_timer_seconds
                FROM steps
                WHERE section_id = ?
                ORDER BY step_index_in_section
                """,
                (section_row["id"],),
            ).fetchall()

            sections.append(
                RecipeSection(
                    name=section_row["name"],
                    ingredients=[
                        Ingredient(name=row["name"], amount=row["amount"], unit=row["unit"])
                        for row in ingredient_rows
                    ],
                    steps=[
                        Step(
                            index=row["global_step_index"],
                            text=row["text"],
                            default_timer_seconds=row["default_timer_seconds"],
                        )
                        for row in step_rows
                    ],
                )
            )

        return Recipe(
            id=recipe_row["id"],
            title=recipe_row["title"],
            servings=recipe_row["servings"],
            sections=sections,
        )

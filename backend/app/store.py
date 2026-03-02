from __future__ import annotations

from collections.abc import Iterable

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
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def update_session(self, session: Session) -> Session:
        self.sessions[session.id] = session
        return session


store = InMemoryStore()

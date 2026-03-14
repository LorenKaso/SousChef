from __future__ import annotations

from ..models import Recipe
from ..repositories.recipe_repository import RecipeRepository


class RecipeService:
    def __init__(self, repository: RecipeRepository | None = None) -> None:
        self.repository = repository or RecipeRepository()

    def add_recipe(self, recipe: Recipe) -> Recipe:
        return self.repository.add(recipe)

    def list_recipes(self) -> list[Recipe]:
        return self.repository.list()

    def get_recipe(self, recipe_id: str) -> Recipe | None:
        return self.repository.get(recipe_id)

    def is_empty(self) -> bool:
        return not self.repository.exists_any()

    def clear(self) -> None:
        self.repository.clear()

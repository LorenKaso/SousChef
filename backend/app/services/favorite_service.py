from __future__ import annotations

from datetime import datetime

from ..models import FavoriteEntry, Recipe
from ..repositories.favorite_repository import FavoriteRepository
from ..repositories.recipe_repository import RecipeRepository


class FavoriteService:
    def __init__(
        self,
        favorite_repository: FavoriteRepository | None = None,
        recipe_repository: RecipeRepository | None = None,
    ) -> None:
        self.favorite_repository = favorite_repository or FavoriteRepository()
        self.recipe_repository = recipe_repository or RecipeRepository()

    def add_favorite(self, recipe_id: str) -> FavoriteEntry:
        """
        Mark a recipe as a favorite.
        Raises ValueError if the recipe is already favorited.
        """
        if self.favorite_repository.exists(recipe_id):
            raise ValueError(f"Recipe {recipe_id!r} is already a favorite.")
        favorited_at_str = self.favorite_repository.add(recipe_id)
        return FavoriteEntry(
            recipe_id=recipe_id,
            favorited_at=datetime.fromisoformat(favorited_at_str),
        )

    def remove_favorite(self, recipe_id: str) -> None:
        """
        Remove a recipe from favorites.
        Raises ValueError if the recipe is not currently favorited.
        """
        removed = self.favorite_repository.remove(recipe_id)
        if not removed:
            raise ValueError(f"Recipe {recipe_id!r} is not in favorites.")

    def is_favorite(self, recipe_id: str) -> bool:
        return self.favorite_repository.exists(recipe_id)

    def list_favorite_recipes(self) -> list[Recipe]:
        """Return full Recipe objects for all favorites, ordered newest-first."""
        ids = self.favorite_repository.list_ids()
        recipes: list[Recipe] = []
        for recipe_id in ids:
            recipe = self.recipe_repository.get(recipe_id)
            if recipe is not None:
                recipes.append(recipe)
        return recipes

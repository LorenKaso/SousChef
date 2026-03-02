from __future__ import annotations

from fastapi import FastAPI

from .api import router
from .models import Ingredient, Recipe, Step
from .store import store


app = FastAPI(title="SousChef Backend", version="0.1.0")
app.include_router(router)


def seed_sample_recipe() -> None:
    if not store.is_empty():
        return

    recipe = Recipe(
        id="recipe-basic-pancakes",
        title="Basic Pancakes",
        servings=2,
        ingredients=[
            Ingredient(name="flour", amount=1.0, unit="cup"),
            Ingredient(name="milk", amount=1.0, unit="cup"),
            Ingredient(name="sugar", amount=1.0, unit="tbsp"),
            Ingredient(name="oil", amount=1.0, unit="tbsp"),
        ],
        steps=[
            Step(index=1, text="Mix flour, sugar, and milk into a smooth batter."),
            Step(index=2, text="Heat a pan and lightly oil it."),
            Step(index=3, text="Pour batter and cook each side until golden."),
        ],
    )
    store.add_recipe(recipe)


@app.on_event("startup")
def on_startup() -> None:
    seed_sample_recipe()

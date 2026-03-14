from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api import router
from .models import Ingredient, Recipe, RecipeSection, Step
from .store import store


def sample_recipes() -> list[Recipe]:
    return [
        Recipe(
            id="recipe-basic-pancakes",
            title="Basic Pancakes",
            servings=2,
            sections=[
                RecipeSection(
                    name="Batter",
                    ingredients=[
                        Ingredient(name="flour", amount=1.0, unit="cup"),
                        Ingredient(name="milk", amount=1.0, unit="cup"),
                        Ingredient(name="sugar", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        Step(index=1, text="Mix flour, sugar, and milk into a smooth batter."),
                    ],
                ),
                RecipeSection(
                    name="Cooking",
                    ingredients=[
                        Ingredient(name="oil", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        Step(index=2, text="Heat a pan and lightly oil it."),
                        Step(index=3, text="Pour batter and cook each side until golden."),
                    ],
                ),
            ],
        ),
        Recipe(
            id="recipe-birthday-chocolate-cake",
            title="Birthday Chocolate Cake",
            servings=8,
            sections=[
                RecipeSection(
                    name="Cake",
                    ingredients=[
                        Ingredient(name="flour", amount=2.0, unit="cup"),
                        Ingredient(name="sugar", amount=1.5, unit="cup"),
                        Ingredient(name="cocoa powder", amount=0.75, unit="cup"),
                        Ingredient(name="milk", amount=1.0, unit="cup"),
                        Ingredient(name="oil", amount=0.5, unit="cup"),
                        Ingredient(name="egg", amount=2.0, unit="unit"),
                    ],
                    steps=[
                        Step(index=1, text="Mix the dry ingredients in a large bowl."),
                        Step(index=2, text="Add milk, oil, and eggs and whisk into a smooth batter."),
                        Step(index=3, text="Pour into a greased cake pan and bake until set."),
                    ],
                ),
                RecipeSection(
                    name="Topping",
                    ingredients=[
                        Ingredient(name="chocolate", amount=150.0, unit="g"),
                        Ingredient(name="cream", amount=0.75, unit="cup"),
                    ],
                    steps=[
                        Step(index=4, text="Warm the cream and stir it into the chocolate until glossy."),
                        Step(index=5, text="Spread the topping over the cooled cake before serving."),
                    ],
                ),
            ],
        ),
        Recipe(
            id="recipe-mushroom-cream-pasta",
            title="Mushroom Cream Pasta",
            servings=4,
            sections=[
                RecipeSection(
                    name="Pasta",
                    ingredients=[
                        Ingredient(name="pasta", amount=400.0, unit="g"),
                        Ingredient(name="salt", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        Step(index=1, text="Boil the pasta in salted water until al dente."),
                        Step(index=2, text="Reserve a little pasta water and drain the pasta."),
                    ],
                ),
                RecipeSection(
                    name="Sauce and Serving",
                    ingredients=[
                        Ingredient(name="mushroom", amount=300.0, unit="g"),
                        Ingredient(name="cream", amount=1.0, unit="cup"),
                        Ingredient(name="butter", amount=2.0, unit="tbsp"),
                        Ingredient(name="parmesan", amount=0.5, unit="cup"),
                        Ingredient(name="black pepper", amount=1.0, unit="tsp"),
                    ],
                    steps=[
                        Step(index=3, text="Cook the mushrooms in butter until browned."),
                        Step(index=4, text="Add cream, parmesan, and black pepper and simmer briefly."),
                        Step(index=5, text="Toss the pasta with the sauce and loosen with pasta water if needed."),
                    ],
                ),
            ],
        ),
    ]


def seed_sample_recipe() -> None:
    if not store.is_empty():
        return

    for recipe in sample_recipes():
        store.add_recipe(recipe)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_sample_recipe()
    yield


app = FastAPI(title="SousChef Backend", version="0.1.0", lifespan=lifespan)
app.include_router(router)

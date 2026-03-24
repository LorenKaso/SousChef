from __future__ import annotations

from .db import init_db
from .models import FlowItem, Ingredient, Recipe, RecipeSection, Step
from .services.recipe_service import RecipeService


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
                        # index 0
                        Ingredient(name="flour", amount=1.0, unit="cup"),
                        # index 1
                        Ingredient(name="milk", amount=1.0, unit="cup"),
                        # index 2
                        Ingredient(name="sugar", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        # index 0
                        Step(index=1, text="Mix flour, sugar, and milk into a smooth batter."),
                    ],
                    execution_flow=[
                        FlowItem(type="ingredient", index=0),  # flour (dry)
                        FlowItem(type="ingredient", index=2),  # sugar (dry)
                        FlowItem(type="ingredient", index=1),  # milk (wet)
                        FlowItem(type="step", index=0),        # mix together
                    ],
                ),
                RecipeSection(
                    name="Cooking",
                    ingredients=[
                        # index 0
                        Ingredient(name="oil", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        # index 0
                        Step(index=2, text="Heat a pan and lightly oil it."),
                        # index 1
                        Step(index=3, text="Pour batter and cook each side until golden."),
                    ],
                    execution_flow=[
                        FlowItem(type="ingredient", index=0),  # oil
                        FlowItem(type="step", index=0),        # heat + oil the pan
                        FlowItem(type="step", index=1),        # pour + cook
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
                        # index 0
                        Ingredient(name="flour", amount=2.0, unit="cup"),
                        # index 1
                        Ingredient(name="sugar", amount=1.5, unit="cup"),
                        # index 2
                        Ingredient(name="cocoa powder", amount=0.75, unit="cup"),
                        # index 3
                        Ingredient(name="milk", amount=1.0, unit="cup"),
                        # index 4
                        Ingredient(name="oil", amount=0.5, unit="cup"),
                        # index 5
                        Ingredient(name="egg", amount=2.0, unit="unit"),
                    ],
                    steps=[
                        # index 0
                        Step(index=1, text="Mix the dry ingredients in a large bowl."),
                        # index 1
                        Step(index=2, text="Add milk, oil, and eggs and whisk into a smooth batter."),
                        # index 2
                        Step(index=3, text="Pour into a greased cake pan and bake until set."),
                    ],
                    execution_flow=[
                        # dry ingredients first
                        FlowItem(type="ingredient", index=0),  # flour
                        FlowItem(type="ingredient", index=1),  # sugar
                        FlowItem(type="ingredient", index=2),  # cocoa powder
                        FlowItem(type="step", index=0),        # mix dry
                        # wet ingredients
                        FlowItem(type="ingredient", index=3),  # milk
                        FlowItem(type="ingredient", index=4),  # oil
                        FlowItem(type="ingredient", index=5),  # eggs
                        FlowItem(type="step", index=1),        # whisk wet in
                        FlowItem(type="step", index=2),        # pour and bake
                    ],
                ),
                RecipeSection(
                    name="Topping",
                    ingredients=[
                        # index 0
                        Ingredient(name="chocolate", amount=150.0, unit="g"),
                        # index 1
                        Ingredient(name="cream", amount=0.75, unit="cup"),
                    ],
                    steps=[
                        # index 0
                        Step(index=4, text="Warm the cream and stir it into the chocolate until glossy."),
                        # index 1
                        Step(index=5, text="Spread the topping over the cooled cake before serving."),
                    ],
                    execution_flow=[
                        FlowItem(type="ingredient", index=0),  # chocolate
                        FlowItem(type="ingredient", index=1),  # cream
                        FlowItem(type="step", index=0),        # warm + stir
                        FlowItem(type="step", index=1),        # spread
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
                        # index 0
                        Ingredient(name="pasta", amount=400.0, unit="g"),
                        # index 1
                        Ingredient(name="salt", amount=1.0, unit="tbsp"),
                    ],
                    steps=[
                        # index 0
                        Step(index=1, text="Boil the pasta in salted water until al dente."),
                        # index 1
                        Step(index=2, text="Reserve a little pasta water and drain the pasta."),
                    ],
                    execution_flow=[
                        FlowItem(type="ingredient", index=0),  # pasta
                        FlowItem(type="ingredient", index=1),  # salt
                        FlowItem(type="step", index=0),        # boil
                        FlowItem(type="step", index=1),        # reserve + drain
                    ],
                ),
                RecipeSection(
                    name="Sauce and Serving",
                    ingredients=[
                        # index 0
                        Ingredient(name="mushroom", amount=300.0, unit="g"),
                        # index 1
                        Ingredient(name="cream", amount=1.0, unit="cup"),
                        # index 2
                        Ingredient(name="butter", amount=2.0, unit="tbsp"),
                        # index 3
                        Ingredient(name="parmesan", amount=0.5, unit="cup"),
                        # index 4
                        Ingredient(name="black pepper", amount=1.0, unit="tsp"),
                    ],
                    steps=[
                        # index 0
                        Step(index=3, text="Cook the mushrooms in butter until browned."),
                        # index 1
                        Step(index=4, text="Add cream, parmesan, and black pepper and simmer briefly."),
                        # index 2
                        Step(index=5, text="Toss the pasta with the sauce and loosen with pasta water if needed."),
                    ],
                    execution_flow=[
                        FlowItem(type="ingredient", index=2),  # butter first
                        FlowItem(type="ingredient", index=0),  # mushrooms into the butter
                        FlowItem(type="step", index=0),        # cook until browned
                        FlowItem(type="ingredient", index=1),  # cream
                        FlowItem(type="ingredient", index=3),  # parmesan
                        FlowItem(type="ingredient", index=4),  # black pepper
                        FlowItem(type="step", index=1),        # simmer
                        FlowItem(type="step", index=2),        # toss with pasta
                    ],
                ),
            ],
        ),
    ]


def ensure_sample_recipes(recipe_service: RecipeService) -> None:
    init_db()
    # Always upsert sample recipes so that execution_flow is kept
    # up-to-date even on an existing database (INSERT OR REPLACE).
    for recipe in sample_recipes():
        recipe_service.add_recipe(recipe)

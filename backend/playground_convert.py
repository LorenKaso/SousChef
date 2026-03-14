from app.models import Ingredient, Recipe, RecipeSection
from app.services.convert import convert_recipe

recipe_metric_source = Recipe(
    id="metric-source",
    title="Metric Source",
    servings=2,
    sections=[
        RecipeSection(
            name="Main",
            ingredients=[
                Ingredient(name="flour", amount=140, unit="g"),
                Ingredient(name="milk", amount=240, unit="ml"),
                Ingredient(name="sugar", amount=12, unit="g"),
                Ingredient(name="egg", amount=2, unit="unit"),
            ],
        )
    ],
)

recipe_volume_source = Recipe(
    id="volume-source",
    title="Volume Source",
    servings=2,
    sections=[
        RecipeSection(
            name="Main",
            ingredients=[
                Ingredient(name="flour", amount=1, unit="cup"),
                Ingredient(name="milk", amount=1, unit="cup"),
                Ingredient(name="sugar", amount=1, unit="tbsp"),
                Ingredient(name="egg", amount=2, unit="unit"),
            ],
        )
    ],
)

print("=== metric source ===")
metric_result = convert_recipe(recipe_metric_source)
for item in metric_result.items:
    print(item.model_dump())

print("\n=== volume source ===")
volume_result = convert_recipe(recipe_volume_source)
for item in volume_result.items:
    print(item.model_dump())

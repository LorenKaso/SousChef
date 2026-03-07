from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
from app.models import Ingredient, Recipe
from app.services.convert import convert_ingredient, convert_recipe
from app.store import store


def setup_function() -> None:
    store.clear()
    seed_sample_recipe()


def test_convert_recipe_endpoint() -> None:
    client = TestClient(app)

    recipes_response = client.get("/recipes")
    assert recipes_response.status_code == 200
    recipes = recipes_response.json()
    assert recipes

    recipe_id = recipes[0]["id"]

    convert_response = client.post(f"/recipes/{recipe_id}/convert")
    assert convert_response.status_code == 200

    payload = convert_response.json()
    assert payload["items"]

    cup_items = [item for item in payload["items"] if item["original_unit"] in {"cup", "cups"}]
    assert cup_items
    assert all(item["ml"] is not None for item in cup_items)
    assert all(item["cups"] is not None for item in cup_items)

    flour_item = next(item for item in payload["items"] if item["name"].lower() == "flour")
    assert flour_item["grams"] is not None


def test_convert_ingredient_tablespoon_to_volume_units() -> None:
    converted = convert_ingredient("sugar", 2.0, "tbsp")

    assert converted.original_amount == 2.0
    assert converted.original_unit == "tbsp"
    assert converted.ml == 30.0
    assert converted.tbsp == 2.0
    assert converted.tsp == 6.0
    assert converted.cups == 30.0 / 240.0
    assert converted.grams is not None


def test_convert_ingredient_teaspoon_to_volume_units() -> None:
    converted = convert_ingredient("sugar", 3.0, "tsp")

    assert converted.original_amount == 3.0
    assert converted.original_unit == "tsp"
    assert converted.ml == 15.0
    assert converted.tsp == 3.0
    assert converted.tbsp == 1.0
    assert converted.cups == 15.0 / 240.0
    assert converted.grams is not None


def test_convert_flour_cup_to_grams_using_catalog() -> None:
    result = convert_ingredient("flour", 1, "cup")

    assert result.name == "flour"
    assert result.original_amount == 1
    assert result.original_unit == "cup"
    assert result.grams is not None
    assert result.grams > 0


def test_convert_known_volume_unit_returns_structured_result() -> None:
    converted = convert_ingredient("sugar", 1.0, "cup")

    assert converted.original_amount == 1.0
    assert converted.original_unit == "cup"
    assert converted.ml == 240.0
    assert converted.cups == 1.0
    assert converted.tbsp == 16.0
    assert converted.tsp == 48.0
    assert converted.grams is not None


def test_egg_without_safe_rule_is_not_force_converted() -> None:
    converted = convert_ingredient("egg", 2.0, "unit")

    assert converted.name == "egg"
    assert converted.original_amount == 2.0
    assert converted.original_unit == "unit"
    assert converted.ml is None
    assert converted.grams is None
    assert converted.cups is None
    assert converted.tbsp is None
    assert converted.tsp is None


def test_unknown_ingredient_does_not_crash() -> None:
    converted = convert_ingredient("mystery_ingredient", 1.0, "cup")

    assert converted.name == "mystery_ingredient"
    assert converted.original_amount == 1.0
    assert converted.original_unit == "cup"
    assert converted.grams is None


def test_unsupported_unit_does_not_crash() -> None:
    converted = convert_ingredient("flour", 3.0, "pinch")

    assert converted.name == "flour"
    assert converted.original_amount == 3.0
    assert converted.original_unit == "pinch"
    assert converted.ml is None
    assert converted.grams is None
    assert converted.cups is None
    assert converted.tbsp is None
    assert converted.tsp is None


def test_missing_safe_rule_preserves_original_values() -> None:
    converted = convert_ingredient("salt", 1.0, "packet")

    assert converted.name == "salt"
    assert converted.original_amount == 1.0
    assert converted.original_unit == "packet"
    assert converted.ml is None
    assert converted.grams is None
    assert converted.cups is None
    assert converted.tbsp is None
    assert converted.tsp is None


def test_egg_without_safe_rule_is_not_force_converted() -> None:
    result = convert_ingredient("egg", 4, "unit")

    assert result.name == "egg"
    assert result.original_amount == 4
    assert result.original_unit == "unit"
    assert result.grams is None


def test_unknown_ingredient_does_not_crash() -> None:
    result = convert_ingredient("dragonfruit", 1, "cup")

    assert result.name == "dragonfruit"
    assert result.original_amount == 1
    assert result.original_unit == "cup"
    assert result.grams is None


def test_convert_recipe_returns_item_for_each_ingredient() -> None:
    recipe = Recipe(
        id="recipe-123",
        title="Simple Cake",
        servings=4,
        ingredients=[
            Ingredient(name="flour", amount=1, unit="cup"),
            Ingredient(name="sugar", amount=2, unit="tbsp"),
            Ingredient(name="egg", amount=2, unit="unit"),
        ],
        steps=[],
    )

    result = convert_recipe(recipe)

    assert result.recipe_id == recipe.id
    assert len(result.items) == 3


def test_convert_recipe_preserves_non_convertible_ingredient() -> None:
    recipe = Recipe(
        id="recipe-egg-safe",
        title="Egg Safe Fallback",
        servings=2,
        ingredients=[
            Ingredient(name="flour", amount=1, unit="cup"),
            Ingredient(name="egg", amount=2, unit="unit"),
        ],
        steps=[],
    )

    result = convert_recipe(recipe)
    egg_item = next((item for item in result.items if item.name == "egg"), None)

    assert egg_item is not None
    assert egg_item.original_amount == 2
    assert egg_item.original_unit == "unit"
    assert egg_item.grams is None


def test_convert_recipe_metric_normalizes_all_safe_ingredients() -> None:
    recipe = Recipe(
        id="recipe-metric-normalize",
        title="Metric Normalization",
        servings=4,
        ingredients=[
            Ingredient(name="flour", amount=1, unit="cup"),
            Ingredient(name="sugar", amount=2, unit="tbsp"),
            Ingredient(name="milk", amount=1, unit="cup"),
            Ingredient(name="egg", amount=2, unit="unit"),
        ],
        steps=[],
    )

    # TDD note: once supported, call convert_recipe(..., target_system="metric").
    result = convert_recipe(recipe)

    assert len(result.items) == 4

    flour_item = next(item for item in result.items if item.name == "flour")
    sugar_item = next(item for item in result.items if item.name == "sugar")
    milk_item = next(item for item in result.items if item.name == "milk")
    egg_item = next(item for item in result.items if item.name == "egg")

    assert flour_item.grams is not None
    assert sugar_item.grams is not None
    assert milk_item.ml is not None

    assert egg_item.original_amount == 2
    assert egg_item.original_unit == "unit"
    assert egg_item.grams is None
    assert egg_item.ml is None


def test_convert_recipe_volume_normalizes_all_safe_ingredients() -> None:
    recipe = Recipe(
        id="recipe-volume-normalize",
        title="Volume Normalization",
        servings=4,
        ingredients=[
            Ingredient(name="flour", amount=140, unit="g"),
            Ingredient(name="sugar", amount=24, unit="g"),
            Ingredient(name="milk", amount=240, unit="ml"),
            Ingredient(name="egg", amount=2, unit="unit"),
        ],
        steps=[],
    )

    # TDD note: once supported, call convert_recipe(..., target_system="volume").
    result = convert_recipe(recipe)

    assert len(result.items) == 4

    flour_item = next(item for item in result.items if item.name == "flour")
    sugar_item = next(item for item in result.items if item.name == "sugar")
    milk_item = next(item for item in result.items if item.name == "milk")
    egg_item = next(item for item in result.items if item.name == "egg")

    assert flour_item.cups is not None
    assert sugar_item.cups is not None or sugar_item.tbsp is not None or sugar_item.tsp is not None
    assert milk_item.cups is not None

    assert egg_item.original_amount == 2
    assert egg_item.original_unit == "unit"
    assert egg_item.cups is None
    assert egg_item.tbsp is None
    assert egg_item.tsp is None

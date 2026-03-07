from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
from app.services.convert import convert_ingredient
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

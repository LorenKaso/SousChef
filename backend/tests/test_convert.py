from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
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

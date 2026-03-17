from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app, seed_sample_recipe
from app.services.rag_service import RagService
from app.store import store


class KeywordEmbedder:
    def __init__(self) -> None:
        self.model_name = "test-keyword-embedder"
        self._features = [
            "flour",
            "baking",
            "powder",
            "maple",
            "oil",
            "water",
            "boiling",
            "מייפל",
            "שמן",
            "מים",
        ]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(feature)) for feature in self._features]


def setup_function() -> None:
    init_db()
    store.clear()
    seed_sample_recipe()


def test_import_structured_recipe_text_creates_usable_recipe() -> None:
    client = TestClient(app)
    response = client.post(
        "/recipes/import/text",
        json={
            "title": "Tomato Pasta",
            "raw_text": (
                "Ingredients\n"
                "- 200 g pasta\n"
                "- 2 tbsp olive oil\n"
                "- 3 tomato\n"
                "\n"
                "Instructions\n"
                "1. Boil the pasta until tender.\n"
                "2. Heat the oil and add the tomato.\n"
                "3. Toss the pasta with the sauce and serve.\n"
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] in {"high", "medium"}
    recipe = payload["recipe"]
    assert recipe["title"] == "Tomato Pasta"
    assert recipe["sections"]
    assert len(recipe["sections"][0]["ingredients"]) == 3
    assert len(recipe["sections"][0]["steps"]) == 3

    recipes_response = client.get("/recipes")
    assert recipes_response.status_code == 200
    imported_ids = [recipe_item["id"] for recipe_item in recipes_response.json()]
    assert recipe["id"] in imported_ids

    session_response = client.post("/session/start", json={"recipe_id": recipe["id"]})
    assert session_response.status_code == 200

    ask_response = client.post(
        f"/session/{session_response.json()['id']}/ask",
        json={"text": "what now"},
    )
    assert ask_response.status_code == 200
    assert "pasta" in ask_response.json()["answer"].lower()


def test_import_messy_recipe_text_falls_back_to_single_section() -> None:
    client = TestClient(app)
    response = client.post(
        "/recipes/import/text",
        json={
            "title": "Messy Soup",
            "raw_text": (
                "1 onion\n"
                "2 cups water\n"
                "1 tsp salt\n"
                "Boil the water with the onion.\n"
                "Stir in the salt and cook for 10 minutes.\n"
                "Serve hot.\n"
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recipe"]["sections"]
    assert len(payload["recipe"]["sections"]) == 1
    assert payload["recipe"]["sections"][0]["steps"]
    assert payload["confidence"] in {"medium", "low"}


def test_import_text_rejects_content_without_usable_steps() -> None:
    client = TestClient(app)
    response = client.post(
        "/recipes/import/text",
        json={
            "title": "Just Ingredients",
            "raw_text": "- 2 eggs\n- 1 cup milk\n- 200 g flour\n",
        },
    )

    assert response.status_code == 422
    assert "steps" in response.json()["detail"].lower()


def test_imported_hebrew_whatsapp_recipe_supports_specific_when_to_add_answers() -> None:
    client = TestClient(app)
    response = client.post(
        "/recipes/import/text",
        json={
            "title": "עוגת מייפל",
            "raw_text": (
                "2 1/2 cups flour + baking powder\n"
                "1 cup maple syrup\n"
                "1 cup oil\n"
                "1 cup boiling water\n"
                "מערבבים את הקמח עם אבקת האפייה ואז מוסיפים את השמן ואת המייפל.\n"
                "לבסוף מוסיפים את המים הרותחים ומערבבים היטב.\n"
            ),
        },
    )

    assert response.status_code == 200
    recipe = response.json()["recipe"]
    assert len(recipe["sections"][0]["ingredients"]) >= 4
    assert len(recipe["sections"][0]["steps"]) >= 3

    session = store.session_service.start_session(recipe["id"])
    rag_service = RagService(
        recipe_service=store.recipe_service,
        session_service=store.session_service,
        embedder=KeywordEmbedder(),
    )

    water_answer = rag_service.answer_question("מתי מוסיפים את המים הרותחים?", session_id=session.id)
    assert water_answer.answer.startswith("מוסיפים את")
    assert "מוסיפים את המים הרותחים" in water_answer.answer

    oil_answer = rag_service.answer_question("מתי מוסיפים את השמן?", session_id=session.id)
    assert oil_answer.answer.startswith("מוסיפים את")
    assert "מוסיפים את השמן" in oil_answer.answer

    maple_answer = rag_service.answer_question("מתי מוסיפים את המייפל?", session_id=session.id)
    assert maple_answer.answer_type == "when_to_add"
    assert maple_answer.answer.startswith("מוסיפים את")
    assert "המייפל" in maple_answer.answer

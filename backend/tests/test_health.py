from fastapi.testclient import TestClient

from app.main import app, seed_sample_recipe
from app.store import store


def setup_function() -> None:
    store.clear()
    seed_sample_recipe()


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

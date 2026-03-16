from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router
from .db import init_db
from .models import Recipe
from .sample_data import ensure_sample_recipes, sample_recipes as _sample_recipes
from .store import store


def sample_recipes() -> list[Recipe]:
    return _sample_recipes()


def seed_sample_recipe() -> None:
    ensure_sample_recipes(store.recipe_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_sample_recipe()
    yield


app = FastAPI(title="SousChef Backend", version="0.1.0", lifespan=lifespan)
app.include_router(router)

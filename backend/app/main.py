from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

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


class UTF8CharsetMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset=" not in content_type.lower():
            response.headers["content-type"] = "application/json; charset=utf-8"
        elif content_type.startswith("text/plain") and "charset=" not in content_type.lower():
            response.headers["content-type"] = "text/plain; charset=utf-8"
        return response


app = FastAPI(title="SousChef Backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(UTF8CharsetMiddleware)
app.include_router(router)

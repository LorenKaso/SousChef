from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from .models import AskRequest, AskResponse, ConvertRecipeResponse, Recipe, Session, StartSessionRequest
from .services.convert import convert_recipe
from .services.orchestrator import process_ask
from .store import store


router = APIRouter()


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.post("/recipes", response_model=Recipe)
def create_recipe(recipe: Recipe) -> Recipe:
    return store.add_recipe(recipe)


@router.get("/recipes", response_model=list[Recipe])
def list_recipes() -> list[Recipe]:
    return list(store.list_recipes())


@router.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: str) -> Recipe:
    recipe = store.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/recipes/{recipe_id}/convert", response_model=ConvertRecipeResponse)
def convert_recipe_endpoint(recipe_id: str) -> ConvertRecipeResponse:
    recipe = store.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return convert_recipe(recipe)


@router.post("/session/start", response_model=Session)
def start_session(payload: StartSessionRequest) -> Session:
    recipe = store.get_recipe(payload.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    session = Session(id=str(uuid.uuid4()), recipe_id=payload.recipe_id)
    return store.add_session(session)


@router.post("/session/{session_id}/ask", response_model=AskResponse)
def ask(session_id: str, payload: AskRequest) -> AskResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    recipe = store.get_recipe(session.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    answer, actions, updated_session = process_ask(session, recipe, payload.text)
    store.update_session(updated_session)
    return AskResponse(answer=answer, actions=actions, session=updated_session)

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import (
    AskRequest,
    AskResponse,
    ConvertRecipeNormalizedResponse,
    ConvertRecipeRequest,
    ImportRecipeTextRequest,
    ImportRecipeTextResponse,
    Recipe,
    Session,
    StartSessionRequest,
    VoiceSessionStartRequest,
    VoiceSessionStartResponse,
    VoiceSessionStopResponse,
    VoiceSessionTurnRequest,
    VoiceSessionTurnResponse,
)
from .services.convert import convert_recipe_normalized
from .services.orchestrator import process_ask
from .services.recipe_import import import_recipe_from_text
from .text_utils import repair_text_if_mojibake
from .store import store


router = APIRouter()


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.post("/recipes", response_model=Recipe)
def create_recipe(recipe: Recipe) -> Recipe:
    return store.recipe_service.add_recipe(recipe)


@router.post("/recipes/import/text", response_model=ImportRecipeTextResponse)
def import_recipe_text(payload: ImportRecipeTextRequest) -> ImportRecipeTextResponse:
    imported = import_recipe_from_text(payload)
    saved = store.add_recipe(imported.recipe)
    return ImportRecipeTextResponse(
        recipe=saved,
        confidence=imported.confidence,
        warnings=imported.warnings,
    )


@router.get("/recipes", response_model=list[Recipe])
def list_recipes() -> list[Recipe]:
    return store.recipe_service.list_recipes()


@router.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: str) -> Recipe:
    recipe = store.recipe_service.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/recipes/{recipe_id}/convert", response_model=ConvertRecipeNormalizedResponse)
def convert_recipe_endpoint(
    recipe_id: str,
    payload: ConvertRecipeRequest,
) -> ConvertRecipeNormalizedResponse:
    recipe = store.recipe_service.get_recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return convert_recipe_normalized(recipe, payload.target_system, payload.language)


@router.post("/session/start", response_model=Session)
def start_session(payload: StartSessionRequest) -> Session:
    recipe = store.recipe_service.get_recipe(payload.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return store.session_service.start_session(payload.recipe_id)


@router.post("/session/{session_id}/ask", response_model=AskResponse)
def ask(session_id: str, payload: AskRequest) -> AskResponse:
    session = store.session_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    recipe = store.recipe_service.get_recipe(session.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    normalized_text = repair_text_if_mojibake(payload.text)
    answer, actions, updated_session = process_ask(
        session,
        recipe,
        normalized_text,
        rag_service=store.rag_service,
    )
    store.session_service.update_session(updated_session)
    return AskResponse(
        answer=repair_text_if_mojibake(answer),
        actions=actions,
        session=updated_session,
    )


@router.post("/voice/session/start", response_model=VoiceSessionStartResponse)
def start_voice_session(payload: VoiceSessionStartRequest) -> VoiceSessionStartResponse:
    return store.voice_orchestrator.start_voice_session(recipe_id=payload.recipe_id)


@router.post("/voice/session/{voice_session_id}/turn", response_model=VoiceSessionTurnResponse)
def voice_turn(
    voice_session_id: str,
    payload: VoiceSessionTurnRequest,
) -> VoiceSessionTurnResponse:
    return store.voice_orchestrator.process_turn(
        voice_session_id=voice_session_id,
        payload=payload,
    )


@router.post("/voice/session/{voice_session_id}/stop", response_model=VoiceSessionStopResponse)
def stop_voice_session(voice_session_id: str) -> VoiceSessionStopResponse:
    return store.voice_orchestrator.stop_voice_session(voice_session_id=voice_session_id)

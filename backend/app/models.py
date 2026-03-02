from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    name: str
    amount: float
    unit: str


class Step(BaseModel):
    index: int
    text: str
    default_timer_seconds: int | None = None


class Recipe(BaseModel):
    id: str
    title: str
    servings: int
    ingredients: list[Ingredient]
    steps: list[Step]


class Session(BaseModel):
    id: str
    recipe_id: str
    current_step: int = 0
    active_timers: list[int] = Field(default_factory=list)


class ActionType(str, Enum):
    START_TIMER = "START_TIMER"
    NEXT_STEP = "NEXT_STEP"
    PREV_STEP = "PREV_STEP"
    HIGHLIGHT_INGREDIENT = "HIGHLIGHT_INGREDIENT"


class Action(BaseModel):
    type: ActionType
    payload: dict[str, Any] = Field(default_factory=dict)


class StartSessionRequest(BaseModel):
    recipe_id: str


class AskRequest(BaseModel):
    text: str


class AskResponse(BaseModel):
    answer: str
    actions: list[Action]
    session: Session

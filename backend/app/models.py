from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


class RecipeSection(BaseModel):
    name: str
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)


class Recipe(BaseModel):
    id: str
    title: str
    servings: int
    sections: list[RecipeSection] = Field(default_factory=list)

    @property
    def ingredients(self) -> list[Ingredient]:
        return [ingredient for section in self.sections for ingredient in section.ingredients]

    @property
    def steps(self) -> list[Step]:
        return [step for section in self.sections for step in section.steps]


class ConvertedIngredient(BaseModel):
    name: str
    original_amount: float
    original_unit: str
    ml: float | None
    grams: float | None
    cups: float | None
    tbsp: float | None
    tsp: float | None
    source: str | None


class ConvertRecipeResponse(BaseModel):
    recipe_id: str
    items: list[ConvertedIngredient]


class ConversionTargetSystem(str, Enum):
    METRIC = "metric"
    VOLUME = "volume"


class DisplayLanguage(str, Enum):
    HE = "he"
    EN = "en"


class ConvertRecipeRequest(BaseModel):
    target_system: ConversionTargetSystem
    language: DisplayLanguage


class NormalizedConvertedIngredient(BaseModel):
    ingredient: str
    original_amount: float
    original_unit: str
    resolved_ingredient_key: str | None = None
    target_amount: float
    target_unit: str
    source: str | None = None


class ConvertRecipeNormalizedResponse(BaseModel):
    recipe_id: str
    display_language: DisplayLanguage = DisplayLanguage.EN
    title: str | None = None
    steps: list[str] = Field(default_factory=list)
    items: list[NormalizedConvertedIngredient]


class Timer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seconds: int
    label: str
    step_index: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PendingTimerProposal(BaseModel):
    seconds: int
    label: str | None = None
    step_index: int | None = None


class Session(BaseModel):
    id: str
    recipe_id: str
    current_section_index: int = 0
    current_phase: str = "ingredients"
    current_item_index: int = 0
    active_timers: list[Timer] = Field(default_factory=list)
    pending_timer: PendingTimerProposal | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def current_step(self) -> int:
        if self.current_phase == "steps":
            return self.current_item_index + 1
        return 1


class ActionType(str, Enum):
    START_TIMER = "START_TIMER"
    TIMER_FINISHED = "TIMER_FINISHED"
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

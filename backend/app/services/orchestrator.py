from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from math import ceil

from ..models import Action, ActionType, Recipe, Session, Timer
from .convert import convert_ingredient
from .conversion_catalog import catalog
from .conversion import build_cup_conversion_answer, needs_cup_conversion, parse_timer_seconds


_NEXT_KEYWORDS = {"next", "×§×“×™×ž×”", "×”×‘×"}
_PREV_KEYWORDS = {"back", "prev", "previous", "××—×•×¨×”", "×—×–×•×¨"}
_WHAT_NOW_KEYWORDS = {"what now", "what's next", "×ž×” ×¢×›×©×™×•", "×ž×” ×”×©×œ×‘ ×”×‘×"}
_TIME_LEFT_KEYWORDS = {"×›×ž×” ×–×ž×Ÿ × ×©××¨", "×–×ž×Ÿ × ×©××¨", "time left", "how much time left"}
_HE_CUP_TO_GRAMS_PATTERN = re.compile(
    r"^\s*\u05db\u05de\u05d4\s+\u05d6\u05d4"
    r"(?:\s+(\d+(?:\.\d+)?))?\s+(\u05db\u05d5\u05e1(?:\u05d5\u05ea)?)\s+(.+?)\s+"
    r"\u05d1\u05d2\u05e8\u05de\u05d9\u05dd\??\s*$"
)
_HE_GRAMS_TO_CUPS_PATTERN = re.compile(
    r"^\s*\u05db\u05de\u05d4\s+\u05db\u05d5\u05e1(?:\u05d5\u05ea)?\s+\u05d6\u05d4\s+"
    r"(\d+(?:\.\d+)?)\s+\u05d2\u05e8\u05dd\s+(.+?)\??\s*$"
)
_HE_RECIPE_INGREDIENT_AMOUNT_PATTERN = re.compile(
    r"^\s*\u05db\u05de\u05d4\s+(.+?)\s+\u05e6\u05e8\u05d9\u05da(?:\s+\u05d1\u05de\u05ea\u05db\u05d5\u05df)?\??\s*$"
)


def _get_current_step_text(recipe: Recipe, current_step: int, lang: str) -> str:
    if not recipe.steps:
        if lang == "he":
            return "\u05d0\u05d9\u05df \u05e9\u05dc\u05d1\u05d9\u05dd \u05d6\u05de\u05d9\u05e0\u05d9\u05dd."
        return "No steps available."

    idx = max(0, min(current_step - 1, len(recipe.steps) - 1))
    step = recipe.steps[idx]
    if lang == "he":
        return f"\u05e9\u05dc\u05d1 {step.index}: {step.text}"
    return f"Step {step.index}: {step.text}"


def _has_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _detect_lang(text: str) -> str:
    return "he" if re.search(r"[\u0590-\u05FF]", text) else "en"


def _build_hebrew_conversion_answer(text: str) -> str | None:
    match = _HE_CUP_TO_GRAMS_PATTERN.match(text)
    if match is None:
        return None

    amount = float(match.group(1)) if match.group(1) is not None else 1.0
    cup_word = match.group(2)
    ingredient_name = match.group(3).strip()

    converted = convert_ingredient(ingredient_name, amount, "cup")
    if converted.grams is None:
        return (
            f"\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d4 \u05d4\u05de\u05e8\u05d4 "
            f"\u05d1\u05d8\u05d5\u05d7\u05d4 \u05dc-{cup_word} {ingredient_name} \u05d1\u05d2\u05e8\u05de\u05d9\u05dd."
        )

    if converted.source == "catalog":
        return f"{cup_word} {ingredient_name} \u05d4\u05d9\u05d0 {converted.grams:.0f} \u05d2\u05e8\u05dd."

    return (
        f"{cup_word} {ingredient_name} \u05d4\u05d9\u05d0 \u05d1\u05e2\u05e8\u05da "
        f"{converted.grams:.0f} \u05d2\u05e8\u05dd."
    )


def _build_hebrew_reverse_conversion_answer(text: str) -> str | None:
    match = _HE_GRAMS_TO_CUPS_PATTERN.match(text)
    if match is None:
        return None

    amount = float(match.group(1))
    ingredient_name = match.group(2).strip()

    converted = convert_ingredient(ingredient_name, amount, "g")
    if converted.cups is None:
        return (
            f"\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d4 \u05d4\u05de\u05e8\u05d4 "
            f"\u05d1\u05d8\u05d5\u05d7\u05d4 \u05dc-{_format_amount(amount)} "
            f"\u05d2\u05e8\u05dd {ingredient_name} \u05dc\u05db\u05d5\u05e1\u05d5\u05ea."
        )

    amount_text = _format_amount(amount)
    cups_text = _format_amount(converted.cups)
    cup_word = _hebrew_unit_label("cup", converted.cups)
    if converted.source == "catalog":
        return f"{amount_text} \u05d2\u05e8\u05dd {ingredient_name} \u05d4\u05dd {cups_text} {cup_word}."

    return (
        f"{amount_text} \u05d2\u05e8\u05dd {ingredient_name} "
        f"\u05d4\u05dd \u05d1\u05e2\u05e8\u05da {cups_text} {cup_word}."
    )


def _format_amount(value: float) -> str:
    return f"{value:g}"


def _hebrew_unit_label(unit: str, amount: float) -> str:
    unit_key = catalog.get_unit_key(unit)
    if unit_key is None:
        return unit

    if unit_key == "cup":
        return "\u05db\u05d5\u05e1" if amount == 1 else "\u05db\u05d5\u05e1\u05d5\u05ea"
    if unit_key == "tbsp":
        return "\u05db\u05e3" if amount == 1 else "\u05db\u05e4\u05d5\u05ea"
    if unit_key == "tsp":
        return "\u05db\u05e4\u05d9\u05ea" if amount == 1 else "\u05db\u05e4\u05d9\u05d5\u05ea"
    if unit_key == "g":
        return "\u05d2\u05e8\u05dd"
    if unit_key == "ml":
        return "\u05de\"\u05dc"

    aliases_he = catalog.raw.get("meta", {}).get("aliases_units", {}).get("he", {})
    if isinstance(aliases_he, dict):
        for alias, canonical in aliases_he.items():
            if isinstance(alias, str) and canonical == unit_key:
                return alias
    return unit


def _hebrew_ingredient_label(name: str) -> str:
    ingredient_key = catalog.get_ingredient_key(name)
    if ingredient_key is None:
        return name

    ingredient_data = catalog.get_ingredient_data(ingredient_key)
    if isinstance(ingredient_data, dict):
        display_name_he = ingredient_data.get("display_name_he")
        if isinstance(display_name_he, str) and display_name_he.strip():
            return display_name_he
    return name


def _find_recipe_ingredient(recipe: Recipe, query_name: str):
    query_key = catalog.get_ingredient_key(query_name)
    normalized_query = query_name.strip().lower()

    for ingredient in recipe.ingredients:
        ingredient_key = catalog.get_ingredient_key(ingredient.name)
        if query_key is not None and ingredient_key == query_key:
            return ingredient
        if ingredient.name.strip().lower() == normalized_query:
            return ingredient
    return None


def _build_hebrew_recipe_ingredient_answer(text: str, recipe: Recipe) -> str | None:
    match = _HE_RECIPE_INGREDIENT_AMOUNT_PATTERN.match(text)
    if match is None:
        return None

    query_name = match.group(1).strip()
    matched = _find_recipe_ingredient(recipe, query_name)
    if matched is None:
        return "\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9 \u05d0\u05ea \u05d4\u05de\u05e6\u05e8\u05da \u05d4\u05d6\u05d4 \u05d1\u05de\u05ea\u05db\u05d5\u05df."

    amount_text = _format_amount(matched.amount)
    unit_text = _hebrew_unit_label(matched.unit, matched.amount)
    # Keep the user's ingredient wording in the answer while lookup stays catalog-based.
    ingredient_text = query_name
    return f"\u05e6\u05e8\u05d9\u05da {amount_text} {unit_text} {ingredient_text}."


def format_duration(seconds: int, lang: str) -> str:
    seconds = max(0,int(seconds))

    if seconds < 60:
        if lang == "he":
            return f"{seconds} ×©× ×™×•×ª"
        return f"{seconds} seconds"

    if seconds < 3600:
        minutes = ceil(seconds / 60)
        if lang == "he":
            return f"{minutes} ×“×§×•×ª"
        return f"{minutes} minutes"

    hours = ceil(seconds / 3600)
    if lang == "he":
        return f"{hours} ×©×¢×•×ª"
    return f"{hours} hours"


def process_ask(session: Session, recipe: Recipe, text: str) -> tuple[str, list[Action], Session]:
    lowered = text.lower()
    lang = _detect_lang(text)
    actions: list[Action] = []

    conversion_answer = _build_hebrew_conversion_answer(text)
    if conversion_answer is not None:
        return conversion_answer, actions, session

    reverse_conversion_answer = _build_hebrew_reverse_conversion_answer(text)
    if reverse_conversion_answer is not None:
        return reverse_conversion_answer, actions, session

    recipe_ingredient_answer = _build_hebrew_recipe_ingredient_answer(text, recipe)
    if recipe_ingredient_answer is not None:
        return recipe_ingredient_answer, actions, session

    if _has_keyword(lowered, _NEXT_KEYWORDS):
        if recipe.steps:
            session.current_step = min(session.current_step + 1, len(recipe.steps))
        actions.append(
            Action(type=ActionType.NEXT_STEP, payload={"current_step": session.current_step})
        )
        answer = _get_current_step_text(recipe, session.current_step, lang)
        return answer, actions, session

    if _has_keyword(lowered, _PREV_KEYWORDS):
        session.current_step = max(session.current_step - 1, 1)
        actions.append(
            Action(type=ActionType.PREV_STEP, payload={"current_step": session.current_step})
        )
        answer = _get_current_step_text(recipe, session.current_step, lang)
        return answer, actions, session

    seconds = parse_timer_seconds(lowered)
    if seconds is not None:
        session.active_timers.append(
            Timer(seconds=seconds, label="Timer", step_index=session.current_step)
        )
        actions.append(Action(type=ActionType.START_TIMER, payload={"seconds": seconds}))
        formatted = format_duration(seconds, lang)
        if lang == "he":
            answer = f"×”×¤×¢×œ×ª×™ ×˜×™×™×ž×¨ ×œ-{formatted}."
        else:
            answer = f"Started a timer for {formatted}."
        return answer, actions, session

    if _has_keyword(lowered, _TIME_LEFT_KEYWORDS):
        if not session.active_timers:
            if lang == "he":
                return "××™×Ÿ ×˜×™×™×ž×¨ ×¤×¢×™×œ.", actions, session
            return "No active timer.", actions, session

        timer = session.active_timers[-1]
        started_at = timer.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        else:
            started_at = started_at.astimezone(timezone.utc)

        now = datetime.now(timezone.utc)
        remaining_seconds = ceil(
            (started_at + timedelta(seconds=timer.seconds) - now).total_seconds()
        )

        if remaining_seconds <= 0:
            session.active_timers = [t for t in session.active_timers if t.id != timer.id]
            actions.append(
                Action(
                    type=ActionType.TIMER_FINISHED,
                    payload={"timer_id": timer.id, "step_index": timer.step_index},
                )
            )
            if lang == "he":
                return "×”×˜×™×™×ž×¨ × ×’×ž×¨.", actions, session
            return "Timer finished.", actions, session

        formatted = format_duration(remaining_seconds, lang)
        if lang == "he":
            return f"× ×©××¨×• {formatted}.", actions, session
        return f"Time left: {formatted}.", actions, session

    if _has_keyword(lowered, _WHAT_NOW_KEYWORDS):
        answer = _get_current_step_text(recipe, session.current_step, lang)
        return answer, actions, session

    if needs_cup_conversion(lowered):
        answer = build_cup_conversion_answer(lowered)
        if answer is None:
            answer = _get_current_step_text(recipe, session.current_step, lang)
        return answer, actions, session

    answer = _get_current_step_text(recipe, session.current_step, lang)
    return answer, actions, session


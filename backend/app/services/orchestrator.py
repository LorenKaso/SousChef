from __future__ import annotations

from .conversion import build_cup_conversion_answer, needs_cup_conversion, parse_timer_seconds
from ..models import Action, ActionType, Recipe, Session, Timer


_NEXT_KEYWORDS = {"next", "קדימה", "הבא"}
_PREV_KEYWORDS = {"back", "prev", "previous",  "אחורה", "חזור"}
_WHAT_NOW_KEYWORDS = {"what now", "what's next",  "מה עכשיו", "מה השלב הבא"}


def _get_current_step_text(recipe: Recipe, current_step: int) -> str:
    if not recipe.steps:
        return "No steps available."

    idx = max(0, min(current_step - 1, len(recipe.steps) - 1))
    step = recipe.steps[idx]
    return f"Step {step.index}: {step.text}"


def _has_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def process_ask(session: Session, recipe: Recipe, text: str) -> tuple[str, list[Action], Session]:
    lowered = text.lower()
    normalized = lowered.strip()
    actions: list[Action] = []

    if normalized == "???":
        actions.append(
            Action(type=ActionType.NEXT_STEP, payload={"current_step": session.current_step})
        )
        answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    if normalized == "?? ?????":
        answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    if _has_keyword(lowered, _NEXT_KEYWORDS):
        if recipe.steps:
            session.current_step = min(session.current_step + 1, len(recipe.steps))
        actions.append(
            Action(type=ActionType.NEXT_STEP, payload={"current_step": session.current_step})
        )
        answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    if _has_keyword(lowered, _PREV_KEYWORDS):
        session.current_step = max(session.current_step - 1, 1)
        actions.append(
            Action(type=ActionType.PREV_STEP, payload={"current_step": session.current_step})
        )
        answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    seconds = parse_timer_seconds(lowered)
    if seconds is not None:
        session.active_timers.append(
            Timer(seconds=seconds, label="Timer", step_index=session.current_step)
        )
        actions.append(Action(type=ActionType.START_TIMER, payload={"seconds": seconds}))
        answer = f"Started a timer for {seconds} seconds."
        return answer, actions, session

    if _has_keyword(lowered, _WHAT_NOW_KEYWORDS):
        answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    if needs_cup_conversion(lowered):
        answer = build_cup_conversion_answer(lowered)
        if answer is None:
            answer = _get_current_step_text(recipe, session.current_step)
        return answer, actions, session

    answer = _get_current_step_text(recipe, session.current_step)
    return answer, actions, session

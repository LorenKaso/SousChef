from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from math import ceil

from ..models import Action, ActionType, Recipe, Session, Timer
from .conversion import build_cup_conversion_answer, needs_cup_conversion, parse_timer_seconds


_NEXT_KEYWORDS = {"next", "קדימה", "הבא"}
_PREV_KEYWORDS = {"back", "prev", "previous", "אחורה", "חזור"}
_WHAT_NOW_KEYWORDS = {"what now", "what's next", "מה עכשיו", "מה השלב הבא"}
_TIME_LEFT_KEYWORDS = {"כמה זמן נשאר", "זמן נשאר", "time left", "how much time left"}


def _get_current_step_text(recipe: Recipe, current_step: int, lang: str) -> str:
    if not recipe.steps:
        if lang == "he":
            return "אין שלבים זמינים."
        return "No steps available."

    idx = max(0, min(current_step - 1, len(recipe.steps) - 1))
    step = recipe.steps[idx]
    if lang == "he":
        return f"שלב {step.index}: {step.text}"
    return f"Step {step.index}: {step.text}"


def _has_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _detect_lang(text: str) -> str:
    return "he" if re.search(r"[\u0590-\u05FF]", text) else "en"


def format_duration(seconds: int, lang: str) -> str:
    seconds = max(0,int(seconds))

    if seconds < 60:
        if lang == "he":
            return f"{seconds} שניות"
        return f"{seconds} seconds"

    if seconds < 3600:
        minutes = ceil(seconds / 60)
        if lang == "he":
            return f"{minutes} דקות"
        return f"{minutes} minutes"

    hours = ceil(seconds / 3600)
    if lang == "he":
        return f"{hours} שעות"
    return f"{hours} hours"


def process_ask(session: Session, recipe: Recipe, text: str) -> tuple[str, list[Action], Session]:
    lowered = text.lower()
    lang = _detect_lang(text)
    actions: list[Action] = []

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
            answer = f"הפעלתי טיימר ל-{formatted}."
        else:
            answer = f"Started a timer for {formatted}."
        return answer, actions, session

    if _has_keyword(lowered, _TIME_LEFT_KEYWORDS):
        if not session.active_timers:
            if lang == "he":
                return "אין טיימר פעיל.", actions, session
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
                return "הטיימר נגמר.", actions, session
            return "Timer finished.", actions, session

        formatted = format_duration(remaining_seconds, lang)
        if lang == "he":
            return f"נשארו {formatted}.", actions, session
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

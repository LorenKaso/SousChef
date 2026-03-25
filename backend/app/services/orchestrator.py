from __future__ import annotations
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from math import ceil
from ..models import (
    Action,
    ActionType,
    FlowItem,
    Ingredient,
    PendingTimerProposal,
    Recipe,
    Session,
    Step,
    Timer,
)
from .rag_service import RagService
from .convert import convert_ingredient, convert_recipe
from .conversion_catalog import catalog
from .conversion import build_cup_conversion_answer, needs_cup_conversion, parse_timer_seconds


_NEXT_KEYWORDS = {"next", "קדימה", "הבא"}
_PREV_KEYWORDS = {"back", "prev", "previous", "אחורה", "חזור"}
_WHAT_NOW_KEYWORDS = {"what now", "what's next", "מה עכשיו", "מה השלב הבא"}
_TIME_LEFT_KEYWORDS = {"כמה זמן נשאר", "זמן נשאר", "time left", "how much time left"}
_DISPLAY_QUERY_COMMANDS = {
    # Show the current item without advancing — "remind me what I should do".
    "what now",
    "what now?",
    "what's next",
    "what's next?",
    "מה עכשיו",
}
# Every entry here advances the session by one item and reads the new current
# item aloud.  Hebrew has two words for "step" (שלב / צעד) and STT output
# varies, so both must be covered.  "הבא" / "קדימה" were previously defined
# in the unused _NEXT_KEYWORDS set and are now wired in here.
_COMPLETION_COMMANDS = {
    # English — bare commands
    "done",
    "completed",
    "i added it",
    "i finished",
    "next",
    "next step",
    "continue",
    "go ahead",
    # English — natural question forms that mean "advance to next"
    "what is the next step",
    "what is the next step?",
    "what's the next step",
    "what's the next step?",
    "what should i do next",
    "what should i do next?",
    "what do i do next",
    "what do i do next?",
    # Hebrew — completion markers
    "שמתי",
    "הוספתי",
    "סיימתי",
    # Hebrew — "next" navigation (שלב = stage, צעד = step)
    "הבא",
    "קדימה",
    "השלב הבא",
    "שלב הבא",
    "מה השלב הבא",
    "הצעד הבא",
    "צעד הבא",
    "מה הצעד הבא",
}
_HE_COMPLETION_PREFIXES = (
    "שמתי",
    "הוספתי",
    "סיימתי",
)
# Filler tokens that STT commonly inserts around navigation commands.
# Used by _core_navigation_text to strip "ok next step" → "next step".
_NAV_FILLER_TOKENS = frozenset({
    # English
    "ok", "okay", "alright", "sure", "please", "um", "uh", "well", "right", "yeah",
    # Hebrew
    "\u05d1\u05d1\u05e7\u05e9\u05d4",  # בבקשה (please)
    "\u05d0\u05d4",                      # אה (um/ah)
})
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
_HE_INGREDIENT_PROGRESS_PATTERN = re.compile(
    r"^\s*(?:\u05e9\u05de\u05ea\u05d9|\u05d4\u05d5\u05e1\u05e4\u05ea\u05d9|"
    r"\u05e1\u05d9\u05d9\u05de\u05ea\u05d9\s+\u05e2\u05dd)\s+(.+?)[\?\.\!]*\s*$"
)
_HE_TIMER_LABEL_PATTERN = re.compile(
    r"(?:\u05e9\u05d9\u05dd|\u05ea\u05e9\u05d9\u05dd|\u05d4\u05e4\u05e2\u05dc(?:\u05d9)?)"
    r"(?:\s+\u05dc\u05d9)?\s+\u05d8\u05d9\u05d9\u05de\u05e8"
    r"(?:\s+(.+?))?\s+\u05dc-?\s*\d+",
    flags=re.IGNORECASE,
)
_HE_TIME_LEFT_PATTERN = re.compile(
    r"^\s*\u05db\u05de\u05d4\s+\u05d6\u05de\u05df\s+\u05e0\u05e9\u05d0\u05e8"
    r"(?:\s+\u05dc(?:\u05d8\u05d9\u05d9\u05de\u05e8\s*)?(.+?))?\??\s*$"
)
_EN_TIME_LEFT_PATTERN = re.compile(
    r"^\s*(?:how much time left|time left)(?:\s+for\s+(.+?))?\??\s*$",
    flags=re.IGNORECASE,
)
_HE_CONFIRMATION_PATTERN = re.compile(
    r"^\s*(?:\u05db\u05df)(?:\s+\u05ea\u05e4\u05e2\u05d9\u05dc(?:\u05d9)?|\s+\u05d1\u05d1\u05e7\u05e9\u05d4)?[\!\.\?]*\s*$"
)
# Matches English "I added <ingredient>" or "I've added <ingredient>".
# Applied to the normalized (lowercased, NFKC) text produced by
# _normalize_command_text so apostrophe variants are already canonical.
_EN_I_ADDED_PATTERN = re.compile(
    r"^i(?:'ve)?\s+added\s+(?:the\s+)?(.+)$",
    re.IGNORECASE,
)
# Matches the wake-word / assistant-name prefix at the start of a transcript,
# followed by punctuation and/or whitespace.  Stripping this before command
# dispatch ensures that "SousChef, next step", "So next step", "סושף הבא"
# and "סו, מה עכשיו" all reach the correct routing layer.
#
# Ordering rule: longer alternatives are listed before shorter ones.
# "sous chef" must come before "su/so", and "סושף" (full Hebrew name) must
# come before "סו" (short prefix), because regex alternation is left-to-right
# and a two-letter prefix that happens to be a valid start of the longer name
# must not short-circuit the match.
#
# "סושף" = samech(ס) vav(ו) shin(ש) pe-sofit(ף) — the standard Hebrew
# transliteration of "SousChef".  The optional [\s\-]? inside also covers the
# spaced form "סו שף" and the hyphenated form "סו-שף".
_WAKE_PREFIX_RE = re.compile(
    r"^(?:sous[\s\-]?chef|\u05e1\u05d5[\s\-]?\u05e9\u05e3|su|sue|so|\u05e1\u05d5|\u05e9\u05d5)[,.\s]+",
    re.IGNORECASE,
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


def _normalize_command_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    normalized = normalized.strip().lower()
    normalized = normalized.strip(" \t\r\n.,!?\"'`")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _core_navigation_text(normalized: str) -> str:
    """Strip internal commas and leading/trailing filler tokens.

    Used only for navigation intent detection — not for parsers that need
    punctuation (conversion patterns, timer labels, etc.).

    Examples:
        "ok next step"  → "next step"
        "next, step"    → "next step"
        "please what now" → "what now"
        "מה עכשיו בבקשה"  → "מה עכשיו"
    """
    # Remove commas — STT inserts them at natural pauses ("next, step").
    scrubbed = normalized.replace(",", " ")
    scrubbed = re.sub(r"\s+", " ", scrubbed).strip()
    tokens = scrubbed.split()
    while tokens and tokens[0] in _NAV_FILLER_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1] in _NAV_FILLER_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def _is_display_query_command(text: str) -> bool:
    normalized = _normalize_command_text(text)
    if normalized in _DISPLAY_QUERY_COMMANDS:
        return True
    core = _core_navigation_text(normalized)
    return bool(core) and core != normalized and core in _DISPLAY_QUERY_COMMANDS


def _is_completion_command(text: str) -> bool:
    normalized = _normalize_command_text(text)
    if normalized in _COMPLETION_COMMANDS:
        return True
    if any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in _HE_COMPLETION_PREFIXES
    ):
        return True
    # Re-check after stripping fillers and internal commas.
    core = _core_navigation_text(normalized)
    if core and core != normalized:
        if core in _COMPLETION_COMMANDS:
            return True
        if any(
            core == prefix or core.startswith(f"{prefix} ")
            for prefix in _HE_COMPLETION_PREFIXES
        ):
            return True
    return False


def _build_completion_message(lang: str) -> str:
    if lang == "he":
        return "\u05e1\u05d9\u05d9\u05de\u05ea \u05d0\u05ea \u05db\u05dc \u05d4\u05de\u05ea\u05db\u05d5\u05df."
    return "You completed the recipe."


def _format_english_unit(unit: str, amount: float) -> str:
    normalized = unit.strip().lower()
    if normalized in {"g", "ml", ""}:
        return unit
    if normalized == "unit":
        return ""
    if amount == 1:
        return unit

    irregular = {
        "cup": "cups",
        "tbsp": "tbsp",
        "tsp": "tsp",
    }
    if normalized in irregular:
        return irregular[normalized]
    if normalized.endswith("s"):
        return unit
    return f"{unit}s"


def _format_english_ingredient_name(name: str, amount: float, unit: str) -> str:
    if unit.strip().lower() != "unit" or amount == 1 or name.endswith("s"):
        return name
    return f"{name}s"


def _build_ingredient_instruction(ingredient: Ingredient, lang: str) -> str:
    amount_text = _format_amount(ingredient.amount)
    if lang == "he":
        ingredient_name = _hebrew_ingredient_label(ingredient.name)
        if ingredient.unit.strip().lower() == "unit":
            return f"\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 {amount_text} {ingredient_name}."
        unit_text = _hebrew_unit_label(ingredient.unit, ingredient.amount)
        return (
            f"\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 "
            f"{amount_text} {unit_text} {ingredient_name}."
        )

    unit_text = _format_english_unit(ingredient.unit, ingredient.amount)
    ingredient_name = _format_english_ingredient_name(
        ingredient.name,
        ingredient.amount,
        ingredient.unit,
    )
    if unit_text:
        return f"Add {amount_text} {unit_text} of {ingredient_name}."
    return f"Add {amount_text} {ingredient_name}."


def _normalize_guided_progress(session: Session, recipe: Recipe) -> bool:
    """Advance session past exhausted sections; return True when recipe is done."""
    while True:
        if session.current_section_index >= len(recipe.sections):
            session.current_phase = "steps"
            session.current_item_index = 0
            return True

        section = recipe.sections[session.current_section_index]

        if section.execution_flow is not None:
            # Flow mode: follow the explicit interleaved sequence.
            if session.current_phase != "flow":
                session.current_phase = "flow"
                session.current_item_index = 0
            if session.current_item_index < len(section.execution_flow):
                return False
        elif session.current_phase == "ingredients":
            # Classic mode: all ingredients first.
            if session.current_item_index < len(section.ingredients):
                return False
            session.current_phase = "steps"
            session.current_item_index = 0
            continue
        else:
            # Classic mode: then all steps.
            if session.current_item_index < len(section.steps):
                return False

        # Section exhausted — move to the next one.
        session.current_section_index += 1
        session.current_phase = "ingredients"
        session.current_item_index = 0


def _resolve_current_guided_item(
    session: Session,
    recipe: Recipe,
) -> tuple[str, Ingredient | Step] | None:
    if _normalize_guided_progress(session, recipe):
        return None

    section = recipe.sections[session.current_section_index]

    if section.execution_flow is not None:
        flow_item = section.execution_flow[session.current_item_index]
        if flow_item.type == "ingredient":
            return "ingredients", section.ingredients[flow_item.index]
        return "steps", section.steps[flow_item.index]

    # Classic mode.
    if session.current_phase == "ingredients":
        return "ingredients", section.ingredients[session.current_item_index]
    return "steps", section.steps[session.current_item_index]


def _flow_item_text(
    section,
    flow_item: FlowItem,
    lang: str,
) -> str:
    """Format a single flow item as a human-readable instruction."""
    if flow_item.type == "ingredient":
        return _build_ingredient_instruction(
            section.ingredients[flow_item.index], lang
        )
    return section.steps[flow_item.index].text


def _peek_next_flow_item_text(
    session: Session, recipe: Recipe, lang: str
) -> str | None:
    """Return the next flow item text without mutating session state."""
    if session.current_section_index >= len(recipe.sections):
        return None
    section = recipe.sections[session.current_section_index]
    if section.execution_flow is None:
        return None
    next_index = session.current_item_index + 1
    if next_index >= len(section.execution_flow):
        return None
    return _flow_item_text(section, section.execution_flow[next_index], lang)


def _current_guided_answer(session: Session, recipe: Recipe, lang: str) -> str:
    current_item = _resolve_current_guided_item(session, recipe)
    if current_item is None:
        return _build_completion_message(lang)

    phase, item = current_item
    answer = (
        _build_ingredient_instruction(item, lang)
        if phase == "ingredients"
        else item.text
    )

    # In flow mode, append a preview of what comes next.
    if session.current_phase == "flow":
        next_text = _peek_next_flow_item_text(session, recipe, lang)
        if next_text is not None:
            if lang == "he":
                answer += f" אחרי זה: {next_text}"
            else:
                answer += f" Next: {next_text}"

    return answer


def _advance_guided_progress(session: Session, recipe: Recipe, lang: str) -> str:
    current_item = _resolve_current_guided_item(session, recipe)
    if current_item is None:
        return _build_completion_message(lang)

    session.current_item_index += 1
    return _current_guided_answer(session, recipe, lang)


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
    if value <= 0:
        return f"{value:g}"
    frac = Fraction(value).limit_denominator(16)
    if abs(float(frac) - value) > 0.02:
        return f"{value:g}"
    whole = frac.numerator // frac.denominator
    remainder = frac - whole
    if remainder == 0:
        return str(whole)
    frac_str = f"{remainder.numerator}/{remainder.denominator}"
    return f"{whole} {frac_str}" if whole > 0 else frac_str


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


def _clean_ingredient_query(name: str) -> str:
    cleaned = name.strip().strip("?.!,")
    cleaned = re.sub(r"^\u05d0\u05ea\s+", "", cleaned)
    cleaned = re.sub(r"^\u05e2\u05dd\s+", "", cleaned)
    if cleaned.startswith("\u05d4") and len(cleaned) > 1:
        cleaned = cleaned[1:]
    return cleaned


def _ingredient_key_for_text(name: str) -> str | None:
    direct_key = catalog.get_ingredient_key(name)
    if direct_key is not None:
        return direct_key
    cleaned = _clean_ingredient_query(name)
    return catalog.get_ingredient_key(cleaned)


def _ingredient_aliases_for_key(key: str) -> list[str]:
    data = catalog.get_ingredient_data(key)
    if not isinstance(data, dict):
        return []

    aliases: list[str] = []
    for field in ("aliases_en", "aliases_he"):
        values = data.get(field, [])
        if isinstance(values, list):
            aliases.extend([v.strip().lower() for v in values if isinstance(v, str) and v.strip()])
    for field in ("display_name_en", "display_name_he"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip().lower())
    return aliases


def _find_step_relevant_ingredient_keys(recipe: Recipe, step_text: str) -> list[str]:
    lowered_step = step_text.lower()
    relevant: list[str] = []

    for ingredient in recipe.ingredients:
        ingredient_key = _ingredient_key_for_text(ingredient.name)
        if ingredient_key is None or ingredient_key in relevant:
            continue

        aliases = _ingredient_aliases_for_key(ingredient_key)
        if any(alias in lowered_step for alias in aliases):
            relevant.append(ingredient_key)
    return relevant


def _build_hebrew_progression_answer(text: str, recipe: Recipe, current_step: int) -> str | None:
    match = _HE_INGREDIENT_PROGRESS_PATTERN.match(text)
    if match is None or not recipe.steps:
        return None

    mentioned_name = _clean_ingredient_query(match.group(1))
    mentioned_key = _ingredient_key_for_text(mentioned_name)
    if mentioned_key is None:
        return None

    idx = max(0, min(current_step - 1, len(recipe.steps) - 1))
    step_text = recipe.steps[idx].text
    relevant_keys = _find_step_relevant_ingredient_keys(recipe, step_text)
    if mentioned_key not in relevant_keys:
        return None

    mentioned_index = relevant_keys.index(mentioned_key)
    preferred_keys = relevant_keys[mentioned_index + 1 :] + relevant_keys[:mentioned_index]
    for next_key in preferred_keys:
        for ingredient in recipe.ingredients:
            key = _ingredient_key_for_text(ingredient.name)
            if key == next_key:
                amount_text = _format_amount(ingredient.amount)
                unit_text = _hebrew_unit_label(ingredient.unit, ingredient.amount)
                next_name = _hebrew_ingredient_label(ingredient.name)
                return (
                    f"\u05de\u05e2\u05d5\u05dc\u05d4. \u05e2\u05db\u05e9\u05d9\u05d5 "
                    f"\u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05d5\u05e1\u05d9\u05e3 "
                    f"{amount_text} {unit_text} {next_name}."
                )

    return "\u05de\u05e6\u05d5\u05d9\u05df. \u05d0\u05e4\u05e9\u05e8 \u05dc\u05e2\u05d1\u05d5\u05e8 \u05dc\u05e9\u05dc\u05d1 \u05d4\u05d1\u05d0."


def _extract_raw_ingredient_mention(text: str, lang: str) -> str | None:
    """Return the bare ingredient name from an 'I added X' / 'שמתי X' phrase.

    Operates on the ORIGINAL text (not pre-normalised) so it can apply the
    appropriate language pattern.  Returns None when the text is not an
    ingredient-mention statement.
    """
    if lang == "he":
        normalized = _normalize_command_text(text)
        match = _HE_INGREDIENT_PROGRESS_PATTERN.match(normalized)
        if match is not None:
            return _clean_ingredient_query(match.group(1))
    else:
        normalized = _normalize_command_text(text)
        match = _EN_I_ADDED_PATTERN.match(normalized)
        if match is not None:
            return match.group(1).strip()
    return None


def _handle_ingredient_mention(
    text: str,
    session: Session,
    recipe: Recipe,
    lang: str,
) -> str | None:
    """Validate an 'I added X' / 'שמתי X' statement against the current item.

    If X names a recipe ingredient and the session is in the ingredient phase:
    - Correct ingredient → advance and return the next item.
    - Wrong ingredient  → return a corrective instruction.

    Returns None when the text is not an ingredient mention, the ingredient
    is not in this recipe, or the current item is a step (not an ingredient).
    The caller must continue with normal routing in the None case.
    """
    raw_name = _extract_raw_ingredient_mention(text, lang)
    if raw_name is None:
        return None

    # Only intercept when the mentioned name resolves to a recipe ingredient.
    matched = _find_recipe_ingredient(recipe, raw_name)
    if matched is None:
        return None

    current_item = _resolve_current_guided_item(session, recipe)
    if current_item is None:
        # Recipe already complete — fall through to the completion message.
        return None

    phase, item = current_item
    if phase != "ingredients" or not isinstance(item, Ingredient):
        # Current item is a step; don't validate ingredient mentions here.
        return None

    # Compare via catalog key first, then by normalised name.
    mentioned_key = _ingredient_key_for_text(matched.name)
    current_key = _ingredient_key_for_text(item.name)
    is_match = (
        (mentioned_key is not None and mentioned_key == current_key)
        or item.name.strip().lower() == matched.name.strip().lower()
    )

    if is_match:
        session.current_item_index += 1
        return _current_guided_answer(session, recipe, lang)

    # Wrong ingredient — guide the user back to the expected one.
    instruction = _build_ingredient_instruction(item, lang)
    if lang == "he":
        return f"\u05e7\u05d5\u05d3\u05dd: {instruction}"
    return f"Not yet \u2014 first: {instruction}"


def _detect_hebrew_recipe_conversion_target(text: str) -> str | None:
    cleaned = text.strip()
    if "\u05de\u05ea\u05db\u05d5\u05df" not in cleaned:
        return None

    if any(token in cleaned for token in ("\u05d2\u05e8\u05dd", "\u05d2\u05e8\u05de\u05d9\u05dd")):
        return "metric"
    if any(token in cleaned for token in ("\u05db\u05d5\u05e1", "\u05db\u05d5\u05e1\u05d5\u05ea")):
        return "volume"
    return None


def _build_hebrew_recipe_conversion_answer(recipe: Recipe, target_system: str) -> str:
    converted = convert_recipe(recipe, target_system=target_system, language="he")
    items = getattr(converted, "items", [])
    lines: list[str] = []
    for item in items:
        ingredient = getattr(item, "ingredient", None)
        amount = getattr(item, "target_amount", None)
        unit = getattr(item, "target_unit", None)
        if isinstance(ingredient, str) and isinstance(amount, (int, float)) and isinstance(unit, str):
            lines.append(f"{ingredient}: {_format_amount(float(amount))} {unit}")

    return "\n".join(lines) if lines else "\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9 \u05de\u05e6\u05e8\u05db\u05d9\u05dd \u05dc\u05d4\u05de\u05e8\u05d4."


def _extract_timer_label(text: str) -> str | None:
    match = _HE_TIMER_LABEL_PATTERN.search(text)
    if match is None:
        return None
    raw_label = match.group(1)
    if raw_label is None:
        return None
    label = raw_label.strip().strip("?.!,")
    return label if label else None


def _is_confirmation(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"yes", "yes please", "sure", "ok"}:
        return True
    return _HE_CONFIRMATION_PATTERN.match(text) is not None


def _infer_implicit_timer_label(text: str) -> str | None:
    lowered = text.lower()

    if any(token in lowered for token in ("\u05dc\u05e2\u05e8\u05d1\u05d1", "\u05e2\u05e8\u05d1\u05d5\u05d1", "\u05e2\u05e8\u05d1\u05d1\u05d9")):
        return "\u05e2\u05e8\u05d1\u05d5\u05d1"
    if any(token in lowered for token in ("\u05dc\u05d4\u05e7\u05e6\u05d9\u05e3", "\u05d4\u05e7\u05e6\u05e4\u05d4", "\u05dc\u05d4\u05e7\u05e6\u05d9\u05e4\u05d4")):
        return "\u05d4\u05e7\u05e6\u05e4\u05d4"
    if any(token in lowered for token in ("\u05de\u05e7\u05e4\u05d9\u05d0", "\u05dc\u05d4\u05db\u05e0\u05d9\u05e1 \u05dc\u05de\u05e7\u05e4\u05d9\u05d0")):
        return "\u05de\u05e7\u05e4\u05d9\u05d0"
    if any(token in lowered for token in ("\u05dc\u05d0\u05e4\u05d5\u05ea", "\u05d0\u05e4\u05d9\u05d9\u05d4", "\u05dc\u05ea\u05e0\u05d5\u05e8")):
        return "\u05d0\u05e4\u05d9\u05d9\u05d4"
    if any(token in lowered for token in ("\u05dc\u05d1\u05e9\u05dc", "\u05d1\u05d9\u05e9\u05d5\u05dc")):
        return "\u05d1\u05d9\u05e9\u05d5\u05dc"
    return None


def _find_duplicate_active_timer(session: Session, label: str, seconds: int) -> Timer | None:
    expected = _normalize_timer_label(label)
    for timer in session.active_timers:
        if timer.seconds != seconds:
            continue
        if _normalize_timer_label(timer.label) == expected:
            return timer
    return None


def _build_timer_started_answer(label: str, formatted: str, lang: str) -> str:
    if lang == "he":
        if label != "Timer":
            return f"\u05d4\u05e4\u05e2\u05dc\u05ea\u05d9 \u05d8\u05d9\u05d9\u05de\u05e8 {label} \u05dc-{formatted}."
        return f"\u05d4\u05e4\u05e2\u05dc\u05ea\u05d9 \u05d8\u05d9\u05d9\u05de\u05e8 \u05dc-{formatted}."
    return f"Started a timer for {formatted}."


def _append_started_timer_action(actions: list[Action], seconds: int, label: str) -> None:
    payload: dict[str, object] = {"seconds": seconds}
    if label != "Timer":
        payload["label"] = label
    actions.append(Action(type=ActionType.START_TIMER, payload=payload))


def _start_timer(
    session: Session,
    actions: list[Action],
    *,
    seconds: int,
    label: str,
    step_index: int,
) -> None:
    session.active_timers.append(Timer(seconds=seconds, label=label, step_index=step_index))
    _append_started_timer_action(actions, seconds, label)


def _normalize_timer_label(label: str) -> str:
    normalized = label.strip().strip("?.!,").lower()
    normalized = re.sub(r"^\u05d8\u05d9\u05d9\u05de\u05e8\s+", "", normalized)
    normalized = re.sub(r"\s+timer$", "", normalized)
    return normalized.strip()


def _parse_time_left_request(text: str) -> tuple[bool, str | None]:
    he_match = _HE_TIME_LEFT_PATTERN.match(text)
    if he_match is not None:
        label = he_match.group(1)
        if label is None:
            return True, None
        cleaned = _normalize_timer_label(label)
        return True, cleaned or None

    en_match = _EN_TIME_LEFT_PATTERN.match(text)
    if en_match is not None:
        label = en_match.group(1)
        if label is None:
            return True, None
        cleaned = _normalize_timer_label(label)
        return True, cleaned or None

    return False, None


def _find_timer_by_label(session: Session, label: str) -> Timer | None:
    normalized_label = _normalize_timer_label(label)
    for timer in reversed(session.active_timers):
        if _normalize_timer_label(timer.label) == normalized_label:
            return timer
    return None


def _format_remaining_minutes_seconds(seconds: int, lang: str) -> str:
    minutes = seconds // 60
    secs = seconds % 60
    if lang == "he":
        if minutes > 0 and secs > 0:
            return f"{minutes} \u05d3\u05e7\u05d5\u05ea \u05d5-{secs} \u05e9\u05e0\u05d9\u05d5\u05ea"
        if minutes > 0:
            return f"{minutes} \u05d3\u05e7\u05d5\u05ea"
        return f"{secs} \u05e9\u05e0\u05d9\u05d5\u05ea"
    if minutes > 0 and secs > 0:
        return f"{minutes} minutes and {secs} seconds"
    if minutes > 0:
        return f"{minutes} minutes"
    return f"{secs} seconds"


def _remaining_seconds(timer: Timer) -> int:
    started_at = timer.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    else:
        started_at = started_at.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    return ceil((started_at + timedelta(seconds=timer.seconds) - now).total_seconds())


def format_duration(seconds: int, lang: str) -> str:
    seconds = max(0,int(seconds))

    if seconds < 60:
        if lang == "he":
            return f"{seconds} \u05e9\u05e0\u05d9\u05d5\u05ea"
        return f"{seconds} seconds"

    if seconds < 3600:
        minutes = ceil(seconds / 60)
        if lang == "he":
            return f"{minutes} \u05d3\u05e7\u05d5\u05ea"
        return f"{minutes} minutes"

    hours = ceil(seconds / 3600)
    if lang == "he":
        return f"{hours} \u05e9\u05e2\u05d5\u05ea"
    return f"{hours} hours"


def process_ask(
    session: Session,
    recipe: Recipe,
    text: str,
    *,
    rag_service: RagService | None = None,
) -> tuple[str, list[Action], Session]:
    lowered = text.lower()
    lang = _detect_lang(text)
    actions: list[Action] = []

    # Strip the assistant wake-word prefix ("Su, ", "So, " etc.) so that
    # "Su, next step" dispatches correctly as "next step" and "Su, when do I
    # add the eggs?" is recognised by both flow and RAG pattern matchers.
    _stripped = _WAKE_PREFIX_RE.sub("", text).strip()
    if _stripped:
        text = _stripped
        lowered = text.lower()

    conversion_answer = _build_hebrew_conversion_answer(text)
    if conversion_answer is not None:
        return conversion_answer, actions, session

    reverse_conversion_answer = _build_hebrew_reverse_conversion_answer(text)
    if reverse_conversion_answer is not None:
        return reverse_conversion_answer, actions, session

    recipe_ingredient_answer = _build_hebrew_recipe_ingredient_answer(text, recipe)
    if recipe_ingredient_answer is not None:
        return recipe_ingredient_answer, actions, session

    target_system = _detect_hebrew_recipe_conversion_target(text)
    if target_system is not None:
        answer = _build_hebrew_recipe_conversion_answer(recipe, target_system)
        return answer, actions, session

    if session.pending_timer is not None and _is_confirmation(text):
        proposal = session.pending_timer
        timer_label = proposal.label or "Timer"
        duplicate = _find_duplicate_active_timer(session, timer_label, proposal.seconds)
        if duplicate is not None:
            session.pending_timer = None
            if lang == "he":
                if timer_label != "Timer":
                    return (
                        f"\u05db\u05d1\u05e8 \u05e7\u05d9\u05d9\u05dd \u05d8\u05d9\u05d9\u05de\u05e8 "
                        f"{timer_label} \u05e4\u05e2\u05d9\u05dc \u05dc-"
                        f"{format_duration(proposal.seconds, lang)}.",
                        actions,
                        session,
                    )
                return (
                    f"\u05db\u05d1\u05e8 \u05e7\u05d9\u05d9\u05dd \u05d8\u05d9\u05d9\u05de\u05e8 "
                    f"\u05e4\u05e2\u05d9\u05dc \u05dc-{format_duration(proposal.seconds, lang)}.",
                    actions,
                    session,
                )
            return "A similar timer is already active.", actions, session

        _start_timer(
            session,
            actions,
            seconds=proposal.seconds,
            label=timer_label,
            step_index=proposal.step_index or session.current_step,
        )
        session.pending_timer = None
        formatted = format_duration(proposal.seconds, lang)
        answer = _build_timer_started_answer(timer_label, formatted, lang)
        return answer, actions, session

    # ── Ingredient-mention progression (must precede display/completion) ──────
    # "שמתי קמח" / "I added flour": advance only when the named ingredient
    # matches the current guided item; redirect to the correct item otherwise.
    ingredient_answer = _handle_ingredient_mention(text, session, recipe, lang)
    if ingredient_answer is not None:
        return ingredient_answer, actions, session

    if _is_display_query_command(text):
        answer = _current_guided_answer(session, recipe, lang)
        return answer, actions, session

    if _is_completion_command(text):
        answer = _advance_guided_progress(session, recipe, lang)
        return answer, actions, session

    seconds = parse_timer_seconds(lowered)
    if seconds is not None:
        explicit_label = _extract_timer_label(text)
        implicit_label = _infer_implicit_timer_label(text)

        # Explicit command -> immediate creation (existing behavior).
        if explicit_label is not None:
            timer_label = explicit_label
            duplicate = _find_duplicate_active_timer(session, timer_label, seconds)
            if duplicate is not None:
                if lang == "he":
                    return (
                        f"\u05db\u05d1\u05e8 \u05e7\u05d9\u05d9\u05dd \u05d8\u05d9\u05d9\u05de\u05e8 "
                        f"{timer_label} \u05e4\u05e2\u05d9\u05dc \u05dc-"
                        f"{format_duration(seconds, lang)}.",
                        actions,
                        session,
                    )
                return "A similar timer is already active.", actions, session

            _start_timer(
                session,
                actions,
                seconds=seconds,
                label=timer_label,
                step_index=session.current_step,
            )
            formatted = format_duration(seconds, lang)
            answer = _build_timer_started_answer(timer_label, formatted, lang)
            return answer, actions, session

        # Implicit instruction -> proposal only, wait for confirmation.
        if implicit_label is not None:
            duplicate = _find_duplicate_active_timer(session, implicit_label, seconds)
            if duplicate is not None:
                return (
                    f"\u05db\u05d1\u05e8 \u05e7\u05d9\u05d9\u05dd \u05d8\u05d9\u05d9\u05de\u05e8 "
                    f"{implicit_label} \u05e4\u05e2\u05d9\u05dc \u05dc-{format_duration(seconds, lang)}.",
                    actions,
                    session,
                )

            session.pending_timer = PendingTimerProposal(
                seconds=seconds,
                label=implicit_label,
                step_index=session.current_step,
            )
            return (
                f"\u05d6\u05d9\u05d4\u05d9\u05ea\u05d9 \u05d8\u05d9\u05d9\u05de\u05e8 "
                f"{implicit_label} \u05dc-{format_duration(seconds, lang)}. "
                f"\u05dc\u05d4\u05e4\u05e2\u05d9\u05dc \u05e2\u05d1\u05d5\u05e8\u05da?",
                actions,
                session,
            )

        # No label intent detected -> keep generic immediate behavior.
        timer_label = "Timer"
        _start_timer(
            session,
            actions,
            seconds=seconds,
            label=timer_label,
            step_index=session.current_step,
        )
        formatted = format_duration(seconds, lang)
        answer = _build_timer_started_answer(timer_label, formatted, lang)
        return answer, actions, session

    is_time_left_query, requested_label = _parse_time_left_request(text)
    if is_time_left_query or _has_keyword(lowered, _TIME_LEFT_KEYWORDS):
        if not session.active_timers:
            if lang == "he":
                return "\u05d0\u05d9\u05df \u05d8\u05d9\u05d9\u05de\u05e8 \u05e4\u05e2\u05d9\u05dc.", actions, session
            return "No active timer.", actions, session

        timer = session.active_timers[-1]
        if requested_label is not None:
            matched_timer = _find_timer_by_label(session, requested_label)
            if matched_timer is None:
                if lang == "he":
                    return (
                        f"\u05dc\u05d0 \u05de\u05e6\u05d0\u05ea\u05d9 \u05d8\u05d9\u05d9\u05de\u05e8 "
                        f"\u05d1\u05e9\u05dd {requested_label}.",
                        actions,
                        session,
                    )
                return f"Could not find a timer named {requested_label}.", actions, session
            timer = matched_timer

        remaining_seconds = _remaining_seconds(timer)

        if remaining_seconds <= 0:
            session.active_timers = [t for t in session.active_timers if t.id != timer.id]
            actions.append(
                Action(
                    type=ActionType.TIMER_FINISHED,
                    payload={"timer_id": timer.id, "step_index": timer.step_index},
                )
            )
            if requested_label is not None and lang == "he":
                return (
                    f"\u05d4\u05d8\u05d9\u05d9\u05de\u05e8 {requested_label} "
                    f"\u05db\u05d1\u05e8 \u05d4\u05e1\u05ea\u05d9\u05d9\u05dd.",
                    actions,
                    session,
                )
            if requested_label is not None:
                return f"The {requested_label} timer has already finished.", actions, session
            if lang == "he":
                return "\u05d4\u05d8\u05d9\u05d9\u05de\u05e8 \u05e0\u05d2\u05de\u05e8.", actions, session
            return "Timer finished.", actions, session

        if requested_label is not None and lang == "he":
            formatted = _format_remaining_minutes_seconds(remaining_seconds, lang)
            return (
                f"\u05e0\u05e9\u05d0\u05e8\u05d5 {formatted} "
                f"\u05dc\u05d8\u05d9\u05d9\u05de\u05e8 {requested_label}.",
                actions,
                session,
            )
        if requested_label is not None:
            formatted = _format_remaining_minutes_seconds(remaining_seconds, lang)
            return f"Time left for {requested_label} timer: {formatted}.", actions, session

        formatted = format_duration(remaining_seconds, lang)
        if lang == "he":
            return f"\u05e0\u05e9\u05d0\u05e8\u05d5 {formatted}.", actions, session
        return f"Time left: {formatted}.", actions, session

    if needs_cup_conversion(lowered):
        answer = build_cup_conversion_answer(lowered)
        if answer is None:
            answer = _current_guided_answer(session, recipe, lang)
        return answer, actions, session

    if rag_service is not None:
        flow_context = _build_flow_context_for_rag(session, recipe, lang)
        # Pass recipe_id explicitly so the vector-store search is always scoped
        # to the active recipe, even if the second session-store lookup inside
        # rag_service._build_context cannot resolve the recipe from session_id.
        grounded = rag_service.answer_question_with_llm(
            text, recipe_id=recipe.id, session_id=session.id, flow_context=flow_context
        )
        return grounded.answer, actions, session

    answer = _current_guided_answer(session, recipe, lang)
    return answer, actions, session


def _build_flow_context_for_rag(
    session: Session, recipe: Recipe, lang: str
) -> str | None:
    """Build a short cooking-position string injected into the LLM prompt."""
    if session.current_section_index >= len(recipe.sections):
        return None
    section = recipe.sections[session.current_section_index]

    if session.current_phase == "flow":
        if section.execution_flow is None:
            return None
        idx = session.current_item_index
        if idx >= len(section.execution_flow):
            return None
        flow_item = section.execution_flow[idx]
        item_text = _flow_item_text(section, flow_item, lang)
        if lang == "he":
            return f"{item_text} (חלק: {section.name})"
        return f"{item_text} (section: {section.name})"

    if session.current_phase == "steps":
        idx = session.current_item_index
        if section.steps and idx < len(section.steps):
            step = section.steps[idx]
            if lang == "he":
                return (
                    f"שלב {step.index}: {step.text} (חלק: {section.name})"
                )
            return f"Step {step.index}: {step.text} (section: {section.name})"

    if session.current_phase == "ingredients":
        idx = session.current_item_index
        if section.ingredients and idx < len(section.ingredients):
            ing = section.ingredients[idx]
            amount = _format_amount(ing.amount)
            if lang == "he":
                unit_text = _hebrew_unit_label(ing.unit, ing.amount)
                return (
                    f"מצרך נוכחי: {amount} {unit_text} {ing.name}"
                    f" (חלק: {section.name})"
                )
            return (
                f"Current ingredient: {amount} {ing.unit} {ing.name}"
                f" (section: {section.name})"
            )

    return None

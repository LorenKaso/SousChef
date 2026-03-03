from __future__ import annotations

import re
from typing import Final

CUP_TO_ML: Final[float] = 240.0
TBSP_TO_ML: Final[float] = 15.0
TSP_TO_ML: Final[float] = 5.0

DENSITY_GRAMS_PER_CUP: dict[str, float] = {
    "flour": 120.0,
    "sugar": 200.0,
    "milk": 240.0,
    "oil": 218.0,
}

_HE_CUP = "\u05db\u05d5\u05e1"
_HE_CUPS = "\u05db\u05d5\u05e1\u05d5\u05ea"
_HE_TBSP = "\u05db\u05e3"
_HE_TBSPS = "\u05db\u05e4\u05d5\u05ea"
_HE_TSP = "\u05db\u05e4\u05d9\u05ea"
_HE_TSPS = "\u05db\u05e4\u05d9\u05d5\u05ea"
_HE_SECOND = "\u05e9\u05e0\u05d9\u05d4"
_HE_SECONDS = "\u05e9\u05e0\u05d9\u05d5\u05ea"
_HE_MINUTE = "\u05d3\u05e7\u05d4"
_HE_MINUTES = "\u05d3\u05e7\u05d5\u05ea"

_CUP_WORDS = rf"(?:cup|cups|{re.escape(_HE_CUP)}|{re.escape(_HE_CUPS)})"
_TBSP_WORDS = rf"(?:tbsp|tablespoons?|{re.escape(_HE_TBSP)}|{re.escape(_HE_TBSPS)})"
_TSP_WORDS = rf"(?:tsp|teaspoons?|{re.escape(_HE_TSP)}|{re.escape(_HE_TSPS)})"

_SEC_WORDS = rf"(?:seconds?|sec|s|{re.escape(_HE_SECOND)}|{re.escape(_HE_SECONDS)})"
_MIN_WORDS = rf"(?:minutes?|min|m|{re.escape(_HE_MINUTE)}|{re.escape(_HE_MINUTES)})"

_NUMBER = r"(\d+(?:\.\d+)?)"
_CUP_KEYWORD_PATTERN = rf"(?<!\w){_CUP_WORDS}(?!\w)"
_CUP_AMOUNT_PATTERN = rf"{_NUMBER}\s*{_CUP_KEYWORD_PATTERN}"


def _safe_search(pattern: str, text: str) -> re.Match[str] | None:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE)
    except re.error:
        return None


def parse_timer_seconds(text: str) -> int | None:
    lowered = text.lower()

    sec_match = _safe_search(rf"(\d+)\s*{_SEC_WORDS}\b", lowered)
    if sec_match:
        return int(sec_match.group(1))

    min_match = _safe_search(rf"(\d+)\s*{_MIN_WORDS}\b", lowered)
    if min_match:
        return int(min_match.group(1)) * 60

    return None


def needs_cup_conversion(text: str) -> bool:
    return _safe_search(_CUP_KEYWORD_PATTERN, text.lower()) is not None


def build_cup_conversion_answer(text: str) -> str | None:
    lowered = text.lower()

    cup_match = _safe_search(_CUP_AMOUNT_PATTERN, lowered)
    if not cup_match:
        return None

    cups = float(cup_match.group(1))
    ml = cups * CUP_TO_ML

    grams_part = ""
    for ingredient, grams_per_cup in DENSITY_GRAMS_PER_CUP.items():
        if ingredient in lowered:
            grams = cups * grams_per_cup
            grams_part = f" (~{grams:.0f}g {ingredient})"
            break

    return f"{cups:g} cups ~= {ml:.0f}ml{grams_part}"


def build_spoon_conversion_answer(text: str) -> str | None:
    lowered = text.lower()

    tbsp_match = _safe_search(rf"{_NUMBER}\s*{_TBSP_WORDS}\b", lowered)
    if tbsp_match:
        n = float(tbsp_match.group(1))
        ml = n * TBSP_TO_ML
        return f"{n:g} tbsp ~= {ml:.0f}ml"

    tsp_match = _safe_search(rf"{_NUMBER}\s*{_TSP_WORDS}\b", lowered)
    if tsp_match:
        n = float(tsp_match.group(1))
        ml = n * TSP_TO_ML
        return f"{n:g} tsp ~= {ml:.0f}ml"

    return None

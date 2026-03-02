from __future__ import annotations

import re

CUP_TO_ML = 240.0

# Approximate grams per cup for a tiny deterministic table.
DENSITY_GRAMS_PER_CUP: dict[str, float] = {
    "flour": 120.0,
    "sugar": 200.0,
    "milk": 240.0,
    "oil": 218.0,
}


def parse_timer_seconds(text: str) -> int | None:
    lowered = text.lower()

    sec_match = re.search(r"(\d+)\s*(seconds?|sec|??????)", lowered)
    if sec_match:
        return int(sec_match.group(1))

    min_match = re.search(r"(\d+)\s*(minutes?|mins?|?????)", lowered)
    if min_match:
        return int(min_match.group(1)) * 60

    if "timer" in lowered:
        generic_number = re.search(r"(\d+)", lowered)
        if generic_number:
            return int(generic_number.group(1))

    return None


def needs_cup_conversion(text: str) -> bool:
    lowered = text.lower()
    return "cup" in lowered or "cups" in lowered or "???" in lowered


def build_cup_conversion_answer(text: str) -> str:
    lowered = text.lower()
    cup_match = re.search(r"(\d+(?:\.\d+)?)\s*(cups?|cup|???(?:??)?)", lowered)
    cups = float(cup_match.group(1)) if cup_match else 1.0
    ml_value = cups * CUP_TO_ML

    found_ingredient = None
    for ingredient in DENSITY_GRAMS_PER_CUP:
        if ingredient in lowered:
            found_ingredient = ingredient
            break

    if found_ingredient is None:
        return f"{cups:g} cup = {ml_value:g} ml."

    grams = cups * DENSITY_GRAMS_PER_CUP[found_ingredient]
    return (
        f"{cups:g} cup {found_ingredient} is about {ml_value:g} ml "
        f"and about {grams:g} grams."
    )

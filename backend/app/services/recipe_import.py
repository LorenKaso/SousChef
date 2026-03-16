from __future__ import annotations

import re
import uuid

from fastapi import HTTPException

from ..models import (
    DisplayLanguage,
    ImportRecipeTextRequest,
    ImportRecipeTextResponse,
    Ingredient,
    Recipe,
    RecipeSection,
    Step,
)


_INGREDIENT_HEADINGS = {
    "ingredients",
    "ingredient",
    "מצרכים",
    "רכיבים",
}
_STEP_HEADINGS = {
    "instructions",
    "instruction",
    "method",
    "preparation",
    "directions",
    "steps",
    "הוראות",
    "אופן הכנה",
    "הכנה",
    "שלבים",
}
_SECTION_BREAK_HEADINGS = _INGREDIENT_HEADINGS | _STEP_HEADINGS
_ACTION_WORDS = (
    "add",
    "mix",
    "stir",
    "cook",
    "boil",
    "bake",
    "heat",
    "pour",
    "serve",
    "toss",
    "drain",
    "reserve",
    "season",
    "simmer",
    "whisk",
    "chop",
    "slice",
    "combine",
    "מוסיפים",
    "להוסיף",
    "מערבבים",
    "לבשל",
    "מבשלים",
    "מחממים",
    "שופכים",
    "מגישים",
    "מטגנים",
    "מערבב",
    "מבשלים",
    "מבשלים",
)
_UNIT_WORDS = (
    "cup",
    "cups",
    "tbsp",
    "tsp",
    "g",
    "kg",
    "ml",
    "l",
    "gram",
    "grams",
    "teaspoon",
    "teaspoons",
    "tablespoon",
    "tablespoons",
    "oz",
    "lb",
    "pinch",
    "clove",
    "cloves",
    "כוס",
    "כוסות",
    "כף",
    "כפות",
    "כפית",
    "כפיות",
    "גרם",
    "גרמים",
    'מ"ל',
    "מיליליטר",
    "מיליליטרים",
)
_AMOUNT_PATTERN = re.compile(
    r"^\s*(?P<amount>\d+(?:[./]\d+)?)\s*(?P<unit>[^\W\d_]+|[^\s]+)?\s+(?P<name>.+?)\s*$",
    re.UNICODE,
)
_LEADING_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")


def import_recipe_from_text(payload: ImportRecipeTextRequest) -> ImportRecipeTextResponse:
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=422, detail="Recipe text is required")

    lines = _prepare_lines(raw_text)
    title = payload.title.strip() if payload.title and payload.title.strip() else _infer_title(lines)
    sections, warnings, confidence = _parse_sections(lines)

    total_steps = sum(len(section.steps) for section in sections)
    if total_steps == 0:
        raise HTTPException(status_code=422, detail="Could not extract usable recipe steps from the text")

    recipe = Recipe(
        id=_build_recipe_id(title),
        title=title,
        servings=1,
        sections=sections,
    )
    return ImportRecipeTextResponse(
        recipe=recipe,
        confidence=confidence,
        warnings=warnings,
    )


def _prepare_lines(raw_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.append(line)
    return lines


def _infer_title(lines: list[str]) -> str:
    if not lines:
        return "Imported Recipe"
    first = _normalize_inline(lines[0])
    if len(first.split()) <= 8 and not _looks_like_step(first) and not _looks_like_ingredient(first):
        return first
    return "Imported Recipe"


def _parse_sections(lines: list[str]) -> tuple[list[RecipeSection], list[str], str]:
    structured = _parse_structured_sections(lines)
    if structured is not None:
        return structured
    return _parse_heuristic_single_section(lines)


def _parse_structured_sections(lines: list[str]) -> tuple[list[RecipeSection], list[str], str] | None:
    current_ingredients: list[Ingredient] = []
    current_steps: list[str] = []
    in_ingredients = False
    in_steps = False
    found_heading = False

    for line in lines:
        heading_key = _normalize_heading(line)
        if heading_key in _INGREDIENT_HEADINGS:
            found_heading = True
            in_ingredients = True
            in_steps = False
            continue
        if heading_key in _STEP_HEADINGS:
            found_heading = True
            in_ingredients = False
            in_steps = True
            continue
        if not found_heading:
            continue

        if in_ingredients:
            ingredient = _parse_ingredient_line(line)
            if ingredient is not None:
                current_ingredients.append(ingredient)
            continue
        if in_steps:
            step = _parse_step_line(line)
            if step is not None:
                current_steps.append(step)

    if not found_heading:
        return None

    warnings: list[str] = []
    if not current_ingredients:
        warnings.append("No ingredient lines were confidently extracted.")
    if not current_steps:
        warnings.append("No step lines were confidently extracted.")

    section = RecipeSection(
        name="Imported Recipe",
        ingredients=current_ingredients,
        steps=_build_steps(current_steps),
    )
    confidence = "high" if current_ingredients and current_steps else "medium"
    return [section], warnings, confidence


def _parse_heuristic_single_section(lines: list[str]) -> tuple[list[RecipeSection], list[str], str]:
    ingredients: list[Ingredient] = []
    steps: list[str] = []
    warnings: list[str] = []

    for line in lines:
        normalized = _normalize_inline(line)
        if not normalized or normalized.lower() == "imported recipe":
            continue
        ingredient = _parse_ingredient_line(normalized)
        if ingredient is not None and not _looks_like_step(normalized):
            ingredients.append(ingredient)
            continue
        step = _parse_step_line(normalized)
        if step is not None:
            steps.append(step)

    if not ingredients:
        warnings.append("Used heuristic fallback with no confident ingredient extraction.")
    if not steps:
        warnings.append("Used heuristic fallback with no confident step extraction.")

    section = RecipeSection(
        name="Imported Recipe",
        ingredients=ingredients,
        steps=_build_steps(steps),
    )
    confidence = "medium" if ingredients and steps else "low"
    return [section], warnings, confidence


def _build_steps(step_lines: list[str]) -> list[Step]:
    return [Step(index=index, text=text) for index, text in enumerate(step_lines, start=1)]


def _parse_ingredient_line(line: str) -> Ingredient | None:
    cleaned = _normalize_inline(_LEADING_BULLET_PATTERN.sub("", line))
    match = _AMOUNT_PATTERN.match(cleaned)
    if match is None:
        return None

    amount_text = match.group("amount")
    unit = (match.group("unit") or "").strip()
    name = match.group("name").strip(" -,:;")
    if not name:
        return None
    if unit and not _looks_like_unit(unit):
        name = f"{unit} {name}".strip()
        unit = ""
    try:
        amount = _parse_amount(amount_text)
    except ValueError:
        return None
    return Ingredient(name=name, amount=amount, unit=unit)


def _parse_step_line(line: str) -> str | None:
    cleaned = _normalize_inline(_LEADING_BULLET_PATTERN.sub("", line)).strip(" -")
    if not cleaned:
        return None
    if _looks_like_heading(cleaned):
        return None
    if _looks_like_step(cleaned):
        return cleaned
    if len(cleaned.split()) >= 6:
        return cleaned
    return None


def _looks_like_unit(value: str) -> bool:
    lowered = value.lower()
    return lowered in _UNIT_WORDS or any(ch.isdigit() for ch in lowered)


def _looks_like_step(line: str) -> bool:
    lowered = line.lower()
    return any(word in lowered for word in _ACTION_WORDS)


def _looks_like_ingredient(line: str) -> bool:
    stripped = _LEADING_BULLET_PATTERN.sub("", line)
    return _AMOUNT_PATTERN.match(stripped) is not None


def _looks_like_heading(line: str) -> bool:
    return _normalize_heading(line) in _SECTION_BREAK_HEADINGS


def _normalize_heading(line: str) -> str:
    normalized = _normalize_inline(line).lower().strip(":")
    return normalized


def _normalize_inline(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _parse_amount(value: str) -> float:
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    return float(value)


def _build_recipe_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9\u0590-\u05FF]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "imported-recipe"
    return f"recipe-imported-{slug[:40]}-{uuid.uuid4().hex[:8]}"

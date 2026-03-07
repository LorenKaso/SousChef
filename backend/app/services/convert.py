from __future__ import annotations

from typing import Any

from ..models import ConvertRecipeResponse, ConvertedIngredient, Recipe
from .conversion_catalog import catalog

def _volume_units_ml() -> dict[str, float]:
    raw_units = catalog.raw.get("meta", {}).get("volume_units_ml", {})
    result: dict[str, float] = {}
    if not isinstance(raw_units, dict):
        return result

    for unit_key, unit_ml in raw_units.items():
        if isinstance(unit_key, str) and isinstance(unit_ml, (int, float)):
            result[unit_key] = float(unit_ml)
    return result


def _grams_per_unit(ingredient_data: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(ingredient_data, dict):
        return {}

    raw = ingredient_data.get("grams_per_unit", {})
    result: dict[str, float] = {}
    if not isinstance(raw, dict):
        return result

    for unit_key, grams in raw.items():
        if isinstance(unit_key, str) and isinstance(grams, (int, float)):
            result[unit_key] = float(grams)
    return result


def _is_liquid_ingredient(name: str) -> bool:
    ingredient_key = catalog.get_ingredient_key(name)
    if ingredient_key is None:
        return False
    ingredient_data = catalog.get_ingredient_data(ingredient_key)
    return isinstance(ingredient_data, dict) and ingredient_data.get("ml_equals_grams") is True


def _with_overrides(
    item: ConvertedIngredient,
    *,
    ml: float | None,
    grams: float | None,
    cups: float | None,
    tbsp: float | None,
    tsp: float | None,
) -> ConvertedIngredient:
    return ConvertedIngredient(
        name=item.name,
        original_amount=item.original_amount,
        original_unit=item.original_unit,
        ml=ml,
        grams=grams,
        cups=cups,
        tbsp=tbsp,
        tsp=tsp,
        source=item.source,
    )


def _normalize_for_metric(item: ConvertedIngredient) -> ConvertedIngredient:
    # Keep graceful fallback unchanged for non-convertible cases.
    if all(value is None for value in (item.ml, item.grams, item.cups, item.tbsp, item.tsp)):
        return item

    if _is_liquid_ingredient(item.name):
        return _with_overrides(
            item,
            ml=item.ml,
            grams=None,
            cups=None,
            tbsp=None,
            tsp=None,
        )

    return _with_overrides(
        item,
        ml=None,
        grams=item.grams,
        cups=None,
        tbsp=None,
        tsp=None,
    )


def _normalize_for_volume(item: ConvertedIngredient) -> ConvertedIngredient:
    # Keep graceful fallback unchanged for non-convertible cases.
    if all(value is None for value in (item.ml, item.grams, item.cups, item.tbsp, item.tsp)):
        return item

    return _with_overrides(
        item,
        ml=None,
        grams=None,
        cups=item.cups,
        tbsp=item.tbsp,
        tsp=item.tsp,
    )


def convert_ingredient(name: str, amount: float, unit: str) -> ConvertedIngredient:
    ml: float | None = None
    grams: float | None = None
    cups: float | None = None
    tbsp: float | None = None
    tsp: float | None = None
    source: str | None = None

    ingredient_key = catalog.get_ingredient_key(name)
    unit_key = catalog.get_unit_key(unit)

    # Unknown ingredient/unit fallback: keep original fields, avoid guessed conversions.
    if ingredient_key is None or unit_key is None:
        return ConvertedIngredient(
            name=name,
            original_amount=amount,
            original_unit=unit,
            ml=None,
            grams=None,
            cups=None,
            tbsp=None,
            tsp=None,
            source=None,
        )

    ingredient_data = catalog.get_ingredient_data(ingredient_key)
    grams_by_unit = _grams_per_unit(ingredient_data)
    volume_by_unit = _volume_units_ml()

    cup_ml = volume_by_unit.get("cup")
    tbsp_ml = volume_by_unit.get("tbsp")
    tsp_ml = volume_by_unit.get("tsp")

    if unit_key in volume_by_unit:
        ml = amount * volume_by_unit[unit_key]
        source = "catalog"
    elif unit_key == "ml":
        ml = amount
        source = "catalog"
    elif unit_key in grams_by_unit:
        grams = amount * grams_by_unit[unit_key]
        source = "catalog"
    elif unit_key == "g":
        grams = amount
        source = "catalog"

    if grams is None and unit_key in grams_by_unit:
        grams = amount * grams_by_unit[unit_key]
        source = "catalog"

    if ml is not None:
        if cup_ml and cup_ml > 0:
            cups = ml / cup_ml
        if tbsp_ml and tbsp_ml > 0:
            tbsp = ml / tbsp_ml
        if tsp_ml and tsp_ml > 0:
            tsp = ml / tsp_ml

        if grams is None:
            if isinstance(ingredient_data, dict) and ingredient_data.get("ml_equals_grams") is True:
                grams = ml
                source = "catalog"
            elif cup_ml and cup_ml > 0 and "cup" in grams_by_unit:
                grams = (ml / cup_ml) * grams_by_unit["cup"]
                source = "catalog"

    if grams is not None and ml is None:
        if isinstance(ingredient_data, dict) and ingredient_data.get("ml_equals_grams") is True:
            ml = grams
        elif cup_ml and cup_ml > 0 and "cup" in grams_by_unit and grams_by_unit["cup"] > 0:
            cups = grams / grams_by_unit["cup"]
            ml = cups * cup_ml

    if ml is not None:
        if cups is None and cup_ml and cup_ml > 0:
            cups = ml / cup_ml
        if tbsp is None and tbsp_ml and tbsp_ml > 0:
            tbsp = ml / tbsp_ml
        if tsp is None and tsp_ml and tsp_ml > 0:
            tsp = ml / tsp_ml

    return ConvertedIngredient(
        name=name,
        original_amount=amount,
        original_unit=unit,
        ml=ml,
        grams=grams,
        cups=cups,
        tbsp=tbsp,
        tsp=tsp,
        source=source,
    )


def convert_recipe(recipe: Recipe, target_system: str | None = None) -> ConvertRecipeResponse:
    items: list[ConvertedIngredient] = [
        convert_ingredient(ingredient.name, ingredient.amount, ingredient.unit)
        for ingredient in recipe.ingredients
    ]

    normalized_target = target_system.strip().lower() if isinstance(target_system, str) else None
    if normalized_target == "metric":
        items = [_normalize_for_metric(item) for item in items]
    elif normalized_target == "volume":
        items = [_normalize_for_volume(item) for item in items]

    return ConvertRecipeResponse(recipe_id=recipe.id, items=items)

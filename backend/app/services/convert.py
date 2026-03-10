from __future__ import annotations

from typing import Any

from ..models import (
    ConversionTargetSystem,
    ConvertRecipeNormalizedResponse,
    ConvertRecipeResponse,
    ConvertedIngredient,
    DisplayLanguage,
    NormalizedConvertedIngredient,
    Recipe,
)
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


def _pick_volume_target_unit(item: ConvertedIngredient) -> tuple[float, str] | None:
    if item.cups is not None and item.cups >= 1:
        return (item.cups, "cup")
    if item.tbsp is not None and item.tbsp >= 1:
        return (item.tbsp, "tbsp")
    if item.tsp is not None:
        return (item.tsp, "tsp")
    return None


def _unit_label(unit_key: str, language: DisplayLanguage) -> str:
    aliases_units = catalog.raw.get("meta", {}).get("aliases_units", {})
    if not isinstance(aliases_units, dict):
        return unit_key

    lang_map = aliases_units.get(language.value, {})
    if not isinstance(lang_map, dict):
        return unit_key

    if language == DisplayLanguage.EN:
        return unit_key

    for alias, canonical in lang_map.items():
        if isinstance(alias, str) and canonical == unit_key:
            return alias
    return unit_key


def _ingredient_display_name(name: str, language: DisplayLanguage) -> tuple[str, str | None]:
    ingredient_key = catalog.get_ingredient_key(name)
    if ingredient_key is None:
        if language == DisplayLanguage.HE:
            return ("\u05de\u05e8\u05db\u05d9\u05d1", None)
        return (name, None)

    ingredient_data = catalog.get_ingredient_data(ingredient_key)
    if not isinstance(ingredient_data, dict):
        return (name, ingredient_key)

    display_key = "display_name_he" if language == DisplayLanguage.HE else "display_name_en"
    display_name = ingredient_data.get(display_key)
    if isinstance(display_name, str) and display_name.strip():
        return (display_name, ingredient_key)

    fallback_name = ingredient_data.get("display_name_en") or ingredient_data.get("display_name_he")
    if isinstance(fallback_name, str) and fallback_name.strip():
        return (fallback_name, ingredient_key)

    return (name, ingredient_key)


def _to_normalized_item(
    item: ConvertedIngredient,
    target_system: ConversionTargetSystem,
    language: DisplayLanguage,
) -> NormalizedConvertedIngredient:
    ingredient_label, ingredient_key = _ingredient_display_name(item.name, language)

    target_amount = item.original_amount
    resolved_original_unit = catalog.get_unit_key(item.original_unit)
    target_unit_key: str | None = None
    source = item.source

    if target_system == ConversionTargetSystem.METRIC:
        if _is_liquid_ingredient(item.name) and item.ml is not None:
            target_amount = item.ml
            target_unit_key = "ml"
        elif item.grams is not None:
            target_amount = item.grams
            target_unit_key = "g"
        else:
            source = source or "original"
    else:
        picked_volume = _pick_volume_target_unit(item)
        if picked_volume is not None:
            target_amount, target_unit_key = picked_volume
        else:
            source = source or "original"

    original_unit_label = (
        _unit_label(resolved_original_unit, language)
        if resolved_original_unit is not None
        else item.original_unit
    )
    target_unit_label = (
        _unit_label(target_unit_key, language)
        if target_unit_key is not None
        else original_unit_label
    )

    return NormalizedConvertedIngredient(
        ingredient=ingredient_label,
        original_amount=item.original_amount,
        original_unit=original_unit_label,
        resolved_ingredient_key=ingredient_key,
        target_amount=target_amount,
        target_unit=target_unit_label,
        source=source,
    )


def _normalized_target_system(target_system: str | None) -> ConversionTargetSystem | None:
    if not isinstance(target_system, str):
        return None
    lowered = target_system.strip().lower()
    if lowered == ConversionTargetSystem.METRIC.value:
        return ConversionTargetSystem.METRIC
    if lowered == ConversionTargetSystem.VOLUME.value:
        return ConversionTargetSystem.VOLUME
    return None


def _normalized_language(language: str | None) -> DisplayLanguage:
    if isinstance(language, str) and language.strip().lower() == DisplayLanguage.EN.value:
        return DisplayLanguage.EN
    return DisplayLanguage.HE


def _convert_items(recipe: Recipe) -> list[ConvertedIngredient]:
    return [
        convert_ingredient(ingredient.name, ingredient.amount, ingredient.unit)
        for ingredient in recipe.ingredients
    ]


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


def convert_recipe(
    recipe: Recipe,
    target_system: str | None = None,
    language: str | None = None,
) -> ConvertRecipeResponse | ConvertRecipeNormalizedResponse:
    items = _convert_items(recipe)

    normalized_target = _normalized_target_system(target_system)
    if normalized_target is None:
        return ConvertRecipeResponse(recipe_id=recipe.id, items=items)

    if normalized_target == ConversionTargetSystem.METRIC:
        items = [_normalize_for_metric(item) for item in items]
    else:
        items = [_normalize_for_volume(item) for item in items]

    display_language = _normalized_language(language)
    normalized_items = [
        _to_normalized_item(item, normalized_target, display_language) for item in items
    ]

    return ConvertRecipeNormalizedResponse(
        recipe_id=recipe.id,
        display_language=display_language,
        title=recipe.title,
        steps=[step.text for step in recipe.steps],
        items=normalized_items,
    )


def convert_recipe_normalized(
    recipe: Recipe,
    target_system: ConversionTargetSystem,
    language: DisplayLanguage,
) -> ConvertRecipeNormalizedResponse:
    converted = _convert_items(recipe)
    if target_system == ConversionTargetSystem.METRIC:
        converted = [_normalize_for_metric(item) for item in converted]
    else:
        converted = [_normalize_for_volume(item) for item in converted]

    items = [_to_normalized_item(item, target_system, language) for item in converted]
    return ConvertRecipeNormalizedResponse(
        recipe_id=recipe.id,
        display_language=language,
        title=recipe.title,
        steps=[step.text for step in recipe.steps],
        items=items,
    )

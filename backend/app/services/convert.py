from __future__ import annotations

from ..models import ConvertRecipeResponse, ConvertedIngredient, Recipe

CUP_ML = 240.0
TBSP_ML = 15.0
TSP_ML = 5.0

DENSITY_GRAMS_PER_CUP: dict[str, float] = {
    "flour": 120.0,
    "sugar": 200.0,
    "milk": 240.0,
    "oil": 218.0,
}

_CUP_UNITS = {"cup", "cups"}
_TBSP_UNITS = {"tbsp", "tablespoon", "tablespoons"}
_TSP_UNITS = {"tsp", "teaspoon", "teaspoons"}
_ML_UNITS = {"ml"}
_GRAM_UNITS = {"g", "gram", "grams"}


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _normalize_unit(unit: str) -> str:
    return unit.strip().lower()


def convert_ingredient(name: str, amount: float, unit: str) -> ConvertedIngredient:
    normalized_name = _normalize_name(name)
    normalized_unit = _normalize_unit(unit)

    ml: float | None = None
    grams: float | None = None
    cups: float | None = None
    tbsp: float | None = None
    tsp: float | None = None
    source: str | None = None

    if normalized_unit in _CUP_UNITS:
        cups = amount
        ml = amount * CUP_ML
    elif normalized_unit in _TBSP_UNITS:
        tbsp = amount
        ml = amount * TBSP_ML
    elif normalized_unit in _TSP_UNITS:
        tsp = amount
        ml = amount * TSP_ML
    elif normalized_unit in _ML_UNITS:
        ml = amount
    elif normalized_unit in _GRAM_UNITS:
        grams = amount

    grams_per_cup = DENSITY_GRAMS_PER_CUP.get(normalized_name)

    # grams -> cups/ml if possible
    if normalized_unit in _GRAM_UNITS and grams is not None and grams_per_cup is not None:
        cups = grams / grams_per_cup
        ml = cups * CUP_ML
        source = "table"

    # if we have ml, derive other volume units
    if ml is not None:
        cups = ml / CUP_ML
        tbsp = ml / TBSP_ML
        tsp = ml / TSP_ML

    # if we have cups and density, derive grams
    if cups is not None and grams_per_cup is not None:
        grams = cups * grams_per_cup
        source = "table"

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


def convert_recipe(recipe: Recipe) -> ConvertRecipeResponse:
    items = [
        convert_ingredient(ingredient.name, ingredient.amount, ingredient.unit)
        for ingredient in recipe.ingredients
    ]
    return ConvertRecipeResponse(recipe_id=recipe.id, items=items)
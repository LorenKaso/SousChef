from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import Recipe


DEFAULT_STEPS_PER_CHUNK = 2


class RecipeChunk(BaseModel):
    id: str
    recipe_id: str
    chunk_type: str
    text: str
    metadata: dict[str, str | int | float | None] = Field(default_factory=dict)


def chunk_recipe(recipe: Recipe, *, steps_per_chunk: int = DEFAULT_STEPS_PER_CHUNK) -> list[RecipeChunk]:
    chunks: list[RecipeChunk] = [
        RecipeChunk(
            id=f"{recipe.id}:summary",
            recipe_id=recipe.id,
            chunk_type="summary",
            text=(
                f"Recipe title: {recipe.title}. "
                f"Servings: {recipe.servings}. "
                f"Sections: {', '.join(section.name for section in recipe.sections)}."
            ),
            metadata={"title": recipe.title, "servings": recipe.servings},
        )
    ]

    for section_index, section in enumerate(recipe.sections):
        if section.ingredients:
            ingredient_lines = [
                f"- {ingredient.amount:g} {ingredient.unit} {ingredient.name}"
                for ingredient in section.ingredients
            ]
            chunks.append(
                RecipeChunk(
                    id=f"{recipe.id}:section:{section_index}:ingredients",
                    recipe_id=recipe.id,
                    chunk_type="ingredients",
                    text=(
                        f"Recipe: {recipe.title}\n"
                        f"Section: {section.name}\n"
                        "Ingredients:\n"
                        f"{chr(10).join(ingredient_lines)}"
                    ),
                    metadata={
                        "title": recipe.title,
                        "section_name": section.name,
                        "section_index": section_index,
                    },
                )
            )

        for chunk_offset in range(0, len(section.steps), max(1, steps_per_chunk)):
            step_slice = section.steps[chunk_offset : chunk_offset + max(1, steps_per_chunk)]
            if not step_slice:
                continue

            step_lines = [f"Step {step.index}: {step.text}" for step in step_slice]
            chunks.append(
                RecipeChunk(
                    id=f"{recipe.id}:section:{section_index}:steps:{chunk_offset}",
                    recipe_id=recipe.id,
                    chunk_type="steps",
                    text=(
                        f"Recipe: {recipe.title}\n"
                        f"Section: {section.name}\n"
                        "Instructions:\n"
                        f"{chr(10).join(step_lines)}"
                    ),
                    metadata={
                        "title": recipe.title,
                        "section_name": section.name,
                        "section_index": section_index,
                        "step_from": step_slice[0].index,
                        "step_to": step_slice[-1].index,
                    },
                )
            )

    return chunks

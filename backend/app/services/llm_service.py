from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Protocol

from ..models import FlowItem, Recipe, RecipeSection
from ..rag.answer_builder import GroundedAnswer
from ..rag.retrieval import RetrievalResponse

logger = logging.getLogger(__name__)

# Matches flow tokens like I0, S2, i1, s3 (case-insensitive).
_FLOW_TOKEN_RE = re.compile(r"\b([IS])(\d+)\b", re.IGNORECASE)


_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")
_DEFAULT_MAX_OUTPUT_TOKENS = 220
_DEFAULT_TEMPERATURE = 0.1
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class LLMProvider(Protocol):
    model_name: str

    def generate(self, prompt: str) -> str:
        ...


class GeminiProvider:
    def __init__(
        self,
        *,
        model_name: str,
        api_key: str,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        types_module: Any | None = None,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> None:
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self._types = types_module or _load_google_genai_types()
        if client is not None:
            self._client = client
            return

        factory = client_factory or _load_google_genai_client
        self._client = factory(api_key=api_key)

    def generate(self, prompt: str) -> str:
        config = self._types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            thinking_config=self._types.ThinkingConfig(thinking_budget=0),
        )
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config,
        )
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        raise RuntimeError("Gemini provider returned an empty response.")


def _load_google_genai_client(*, api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def _load_google_genai_types() -> Any:
    from google.genai import types

    return types


def detect_answer_language(question: str) -> str:
    return "he" if _HEBREW_CHAR_PATTERN.search(question) else "en"


def build_grounded_answer_prompt(
    *,
    question: str,
    retrieval: RetrievalResponse,
    answer_language: str,
    flow_context: str | None = None,
) -> str:
    context_blocks: list[str] = []
    for index, result in enumerate(retrieval.results, start=1):
        chunk = result.chunk
        context_blocks.append(
            "\n".join(
                [
                    f"[Chunk {index}]",
                    f"id: {chunk.id}",
                    f"recipe_id: {chunk.recipe_id}",
                    f"chunk_type: {chunk.chunk_type}",
                    f"text: {chunk.text}",
                ]
            )
        )

    context_text = (
        "\n\n".join(context_blocks) if context_blocks else "<no context>"
    )
    language_instruction = "Hebrew" if answer_language == "he" else "English"

    position_block = (
        f"The cook is currently at: {flow_context}\n"
        "Answer relative to this position when the question is"
        " about what to do now or next.\n\n"
        if flow_context
        else ""
    )
    return (
        "You are a chef guiding a home cook"
        " through this recipe in real time.\n"
        f"Answer language: {language_instruction}.\n"
        "Give a focused, practical answer to the exact question asked.\n"
        "Base your answer only on the recipe context below.\n"
        "Do not invent ingredients, quantities, steps, timings,"
        " or section names.\n"
        "Keep the answer short and actionable — one or two sentences.\n\n"
        f"{position_block}"
        f"Question: {question}\n\n"
        f"Recipe context:\n{context_text}\n"
    )


def build_gemini_provider_from_env(
    *,
    api_key_env_var: str = "GEMINI_API_KEY",
    model_env_var: str = "GEMINI_MODEL",
    client_factory: Callable[..., Any] | None = None,
    types_module: Any | None = None,
) -> GeminiProvider | None:
    api_key = os.getenv(api_key_env_var, "").strip()
    if not api_key:
        return None

    model_name = os.getenv(model_env_var, "").strip() or _DEFAULT_GEMINI_MODEL
    return GeminiProvider(
        model_name=model_name,
        api_key=api_key,
        client_factory=client_factory,
        types_module=types_module,
    )


def _build_flow_inference_prompt(section: RecipeSection) -> str:
    ings_lines = "\n".join(
        f"I{i}: {ing.name} ({ing.amount} {ing.unit})"
        for i, ing in enumerate(section.ingredients)
    )
    steps_lines = "\n".join(
        f"S{i}: {step.text}" for i, step in enumerate(section.steps)
    )
    return (
        "You are a cooking assistant. Produce the interleaved"
        " execution order for one recipe section.\n\n"
        "Rules:\n"
        "1. Place each ingredient immediately before the first step"
        " that uses it — not all at the top.\n"
        "   Do NOT front-load all ingredients unless the recipe"
        " genuinely requires them all before any step begins.\n"
        "2. Steps must keep their original relative order"
        " (S0 before S1 before S2, etc.).\n"
        "3. Every ingredient and every step must appear exactly once.\n"
        "4. Output ONLY a space-separated token sequence."
        " No explanation, no extra text.\n"
        "   I<n> = the n-th ingredient (0-indexed)."
        " S<n> = the n-th step (0-indexed).\n\n"
        "Example — 3 ingredients, 2 steps:\n"
        "  Wrong (front-loaded):  I0 I1 I2 S0 S1\n"
        "  Correct (interleaved): I0 I1 S0 I2 S1\n"
        "  (I2 is placed just before S1 because S1 is the first"
        " step that uses it)\n\n"
        f"Section: {section.name}\n\n"
        f"Ingredients:\n{ings_lines}\n\n"
        f"Steps:\n{steps_lines}\n\n"
        "Execution order:"
    )


def _parse_flow_tokens(
    text: str,
    n_ingredients: int,
    n_steps: int,
) -> list[FlowItem] | None:
    """Parse and validate an LLM-generated flow token sequence.

    Returns None if the sequence is invalid (duplicates, out-of-range,
    or incomplete coverage).
    """
    tokens = _FLOW_TOKEN_RE.findall(text)
    seen: set[str] = set()
    flow: list[FlowItem] = []

    for kind, idx_str in tokens:
        kind = kind.upper()
        idx = int(idx_str)
        key = f"{kind}{idx}"

        if key in seen:
            return None  # duplicate token
        seen.add(key)

        if kind == "I":
            if idx >= n_ingredients:
                return None  # out of range
            flow.append(FlowItem(type="ingredient", index=idx))
        else:
            if idx >= n_steps:
                return None  # out of range
            flow.append(FlowItem(type="step", index=idx))

    # Verify full coverage.
    expected = {f"I{i}" for i in range(n_ingredients)} | {
        f"S{i}" for i in range(n_steps)
    }
    if seen != expected:
        return None

    return flow


def _infer_section_flow(
    section: RecipeSection,
    provider: "LLMProvider",
) -> list[FlowItem] | None:
    """Ask the LLM for the interleaved execution order of one section."""
    if not section.ingredients or not section.steps:
        return None
    prompt = _build_flow_inference_prompt(section)
    try:
        response = provider.generate(prompt)
    except Exception:
        logger.warning(
            "Flow inference LLM call failed for section %r", section.name
        )
        return None
    flow = _parse_flow_tokens(
        response, len(section.ingredients), len(section.steps)
    )
    if flow is None:
        logger.warning(
            "Flow inference produced invalid tokens for section %r: %r",
            section.name,
            response[:120],
        )
    return flow


def infer_execution_flows(
    recipe: Recipe,
    provider: "LLMProvider | None",
) -> Recipe:
    """Return a copy of the recipe with execution_flow inferred for each
    section that does not already have one.

    Sections with fewer than one ingredient or one step are skipped.
    Any inference failure leaves the section unchanged (classic mode).
    """
    if provider is None:
        return recipe

    enriched: list[RecipeSection] = []
    for section in recipe.sections:
        if section.execution_flow is not None:
            enriched.append(section)
            continue
        flow = _infer_section_flow(section, provider)
        if flow is not None:
            enriched.append(
                section.model_copy(update={"execution_flow": flow})
            )
        else:
            enriched.append(section)

    return recipe.model_copy(update={"sections": enriched})


class LLMService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = (
            provider if provider is not None
            else build_gemini_provider_from_env()
        )

    def is_available(self) -> bool:
        return self.provider is not None

    def has_useful_context(self, retrieval: RetrievalResponse) -> bool:
        return bool(retrieval.results)

    def build_prompt(
        self,
        *,
        question: str,
        retrieval: RetrievalResponse,
        answer_language: str | None = None,
        flow_context: str | None = None,
    ) -> str:
        language = answer_language or detect_answer_language(question)
        return build_grounded_answer_prompt(
            question=question,
            retrieval=retrieval,
            answer_language=language,
            flow_context=flow_context,
        )

    def generate_grounded_answer(
        self,
        *,
        question: str,
        retrieval: RetrievalResponse,
        answer_language: str | None = None,
        flow_context: str | None = None,
    ) -> GroundedAnswer:
        language = answer_language or detect_answer_language(question)

        if not self.has_useful_context(retrieval):
            return GroundedAnswer(
                answer=(
                    "לא מצאתי מספיק הקשר מבוסס מתכון כדי לענות בבטחה."
                    if language == "he"
                    else "I could not find enough grounded recipe"
                    " context to answer safely."
                ),
                answer_type="llm_no_context",
                sources=[],
            )

        if self.provider is None:
            return GroundedAnswer(
                answer=(
                    "לא נמצא ספק LLM פעיל, ולכן לא נוצרה תשובה מבוססת הקשר."
                    if language == "he"
                    else "No active LLM provider is configured,"
                    " so no grounded LLM answer was produced."
                ),
                answer_type="llm_unavailable",
                sources=[result.chunk.id for result in retrieval.results],
            )

        prompt = self.build_prompt(
            question=question,
            retrieval=retrieval,
            answer_language=language,
            flow_context=flow_context,
        )
        answer = self.provider.generate(prompt).strip()
        return GroundedAnswer(
            answer=answer,
            answer_type="llm_grounded",
            sources=[result.chunk.id for result in retrieval.results],
        )

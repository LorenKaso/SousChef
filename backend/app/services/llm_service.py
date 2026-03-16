from __future__ import annotations

import os
import re
from typing import Any, Callable, Protocol

from ..rag.answer_builder import GroundedAnswer
from ..rag.retrieval import RetrievalResponse


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

    context_text = "\n\n".join(context_blocks) if context_blocks else "<no context>"
    language_instruction = "Hebrew" if answer_language == "he" else "English"

    return (
        "You are generating a cooking assistant answer.\n"
        f"Answer language: {language_instruction}.\n"
        "Use only the provided context.\n"
        "Answer strictly from the retrieved recipe chunks.\n"
        "If the context does not support the answer, say that there is not enough grounded context.\n"
        "Do not invent recipe details, ingredients, quantities, steps, timings, or section names.\n"
        "If the answer is uncertain, prefer stating that the grounded context is insufficient.\n"
        "Keep the answer short, direct, and grounded.\n\n"
        f"User question: {question}\n\n"
        f"Context:\n{context_text}\n"
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


class LLMService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider if provider is not None else build_gemini_provider_from_env()

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
    ) -> str:
        language = answer_language or detect_answer_language(question)
        return build_grounded_answer_prompt(
            question=question,
            retrieval=retrieval,
            answer_language=language,
        )

    def generate_grounded_answer(
        self,
        *,
        question: str,
        retrieval: RetrievalResponse,
        answer_language: str | None = None,
    ) -> GroundedAnswer:
        language = answer_language or detect_answer_language(question)

        if not self.has_useful_context(retrieval):
            return GroundedAnswer(
                answer=(
                    "לא מצאתי מספיק הקשר מבוסס מתכון כדי לענות בבטחה."
                    if language == "he"
                    else "I could not find enough grounded recipe context to answer safely."
                ),
                answer_type="llm_no_context",
                sources=[],
            )

        if self.provider is None:
            return GroundedAnswer(
                answer=(
                    "לא נמצא ספק LLM פעיל, ולכן לא נוצרה תשובה מבוססת הקשר."
                    if language == "he"
                    else "No active LLM provider is configured, so no grounded LLM answer was produced."
                ),
                answer_type="llm_unavailable",
                sources=[result.chunk.id for result in retrieval.results],
            )

        prompt = self.build_prompt(
            question=question,
            retrieval=retrieval,
            answer_language=language,
        )
        answer = self.provider.generate(prompt).strip()
        return GroundedAnswer(
            answer=answer,
            answer_type="llm_grounded",
            sources=[result.chunk.id for result in retrieval.results],
        )

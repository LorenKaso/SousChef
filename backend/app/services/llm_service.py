from __future__ import annotations

import re
from typing import Protocol

from ..rag.answer_builder import GroundedAnswer
from ..rag.retrieval import RetrievalResponse


_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")


class LLMProvider(Protocol):
    model_name: str

    def generate(self, prompt: str) -> str:
        ...


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
        "If the context does not support the answer, say that there is not enough grounded context.\n"
        "Do not invent recipe details, ingredients, quantities, steps, or timings.\n"
        "Keep the answer short, direct, and grounded.\n\n"
        f"User question: {question}\n\n"
        f"Context:\n{context_text}\n"
    )


class LLMService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider

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
                    "שכבת ה-LLM עדיין לא מחוברת לספק פעיל."
                    if language == "he"
                    else "The LLM answer layer is not connected to an active provider yet."
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

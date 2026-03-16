from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..services.conversion_catalog import catalog
from .chunking import RecipeChunk
from .retrieval import RetrievalResponse, RetrievalResult


_AMOUNT_PATTERNS = (
    re.compile(r"how much\s+(?P<ingredient>.+?)\s+(?:is|are)\s+in\s+the\s+recipe\??$", re.IGNORECASE),
    re.compile(r"how much\s+(?P<ingredient>.+?)\s+do\s+i\s+need\??$", re.IGNORECASE),
)
_WHEN_ADD_PATTERN = re.compile(r"when\s+do\s+i\s+add\s+(?P<ingredient>.+?)\??$", re.IGNORECASE)
_SECTION_INGREDIENTS_PATTERN = re.compile(
    r"what\s+is\s+in\s+the\s+(?P<section>.+?)\??$",
    re.IGNORECASE,
)
_SECTION_INGREDIENTS_ALT_PATTERN = re.compile(
    r"what\s+goes\s+in\s+the\s+(?P<section>.+?)\??$",
    re.IGNORECASE,
)
_HE_AMOUNT_PATTERNS = (
    re.compile(r"^\s*כמה\s+(?P<ingredient>.+?)\s+יש\s+במתכון\??\s*$"),
    re.compile(r"^\s*כמה\s+(?P<ingredient>.+?)\s+צריך(?:ים)?\??\s*$"),
)
_HE_WHEN_ADD_PATTERN = re.compile(r"^\s*מתי\s+מוסיפ(?:ים|ות)\s+(?:את\s+)?(?P<ingredient>.+?)\??\s*$")
_HE_SECTION_INGREDIENTS_PATTERNS = (
    re.compile(r"^\s*מה\s+יש\s+בחלק\s+של\s+(?P<section>.+?)\??\s*$"),
    re.compile(r"^\s*מה\s+יש\s+ב(?P<section>.+?)\??\s*$"),
)
_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")
_SECTION_NAME_TRANSLATIONS = {
    "Batter": "הבלילה",
    "Cooking": "הבישול",
    "Cake": "העוגה",
    "Topping": "הציפוי",
    "Pasta": "הפסטה",
    "Sauce and Serving": "הרוטב וההגשה",
}
_UNIT_TRANSLATIONS = {
    "g": "גרם",
    "ml": 'מ"ל',
    "cup": "כוס",
    "tbsp": "כף",
    "tsp": "כפית",
    "unit": "",
}


class GroundedAnswer(BaseModel):
    answer: str
    answer_type: str
    sources: list[str] = Field(default_factory=list)


class QueryIntent(BaseModel):
    question_type: str
    requested_section: str | None = None


class RagAnswerBuilder:
    def supports_query(self, query: str) -> bool:
        return self.analyze_query(query) is not None

    def analyze_query(self, query: str) -> QueryIntent | None:
        question_type = self._detect_question_type(query)
        if question_type is None:
            return None

        requested_section = None
        if question_type == "section_ingredients":
            requested_section = self._extract_requested_section(query)
        return QueryIntent(
            question_type=question_type,
            requested_section=requested_section,
        )

    def build(self, query: str, retrieval: RetrievalResponse) -> GroundedAnswer:
        lowered_query = query.strip().lower()
        is_hebrew = _is_hebrew_text(query)
        intent = self.analyze_query(query)
        question_type = intent.question_type if intent is not None else None

        if question_type == "ingredient_amount":
            ingredient_amount = self._extract_ingredient_amount(
                lowered_query,
                retrieval.results,
                is_hebrew=is_hebrew,
            )
            if ingredient_amount is not None:
                return ingredient_amount

        if question_type == "when_to_add":
            when_to_add = self._extract_when_to_add(
                lowered_query,
                retrieval.results,
                is_hebrew=is_hebrew,
            )
            if when_to_add is not None:
                return when_to_add

        if question_type == "section_ingredients":
            section_contents = self._extract_section_contents(
                lowered_query,
                retrieval.results,
                is_hebrew=is_hebrew,
            )
            if section_contents is not None:
                return section_contents

        return self._fallback(retrieval.results, is_hebrew=is_hebrew)

    def _detect_question_type(self, query: str) -> str | None:
        stripped = query.strip()
        lowered = stripped.lower()
        patterns = (
            ("ingredient_amount", _AMOUNT_PATTERNS),
            ("when_to_add", (_WHEN_ADD_PATTERN,)),
            ("section_ingredients", (_SECTION_INGREDIENTS_PATTERN, _SECTION_INGREDIENTS_ALT_PATTERN)),
        )
        hebrew_patterns = (
            ("ingredient_amount", _HE_AMOUNT_PATTERNS),
            ("when_to_add", (_HE_WHEN_ADD_PATTERN,)),
            ("section_ingredients", _HE_SECTION_INGREDIENTS_PATTERNS),
        )

        active_patterns = hebrew_patterns if _is_hebrew_text(stripped) else patterns
        for question_type, question_patterns in active_patterns:
            if any(pattern.match(lowered) for pattern in question_patterns):
                return question_type
        return None

    def _extract_requested_section(self, query: str) -> str | None:
        lowered = query.strip().lower()
        patterns = (
            _HE_SECTION_INGREDIENTS_PATTERNS
            if _is_hebrew_text(query)
            else (_SECTION_INGREDIENTS_PATTERN, _SECTION_INGREDIENTS_ALT_PATTERN)
        )
        for pattern in patterns:
            match = pattern.match(lowered)
            if match is not None:
                section = match.group("section").strip().rstrip("?")
                return section or None
        return None

    def _extract_ingredient_amount(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        is_hebrew: bool,
    ) -> GroundedAnswer | None:
        ingredient_name = None
        patterns = _HE_AMOUNT_PATTERNS if is_hebrew else _AMOUNT_PATTERNS
        for pattern in patterns:
            match = pattern.match(query)
            if match is not None:
                ingredient_name = match.group("ingredient").strip()
                break
        if ingredient_name is None:
            return None

        for result in results:
            if result.chunk.chunk_type != "ingredients":
                continue
            for amount, unit, name in _parse_ingredient_lines(result.chunk):
                if _ingredient_matches(name, ingredient_name):
                    display_name = _format_ingredient_name(name, is_hebrew=is_hebrew)
                    display_unit = _format_unit(unit, amount, is_hebrew=is_hebrew)
                    return GroundedAnswer(
                        answer=(
                            f"במתכון יש {amount} {display_unit} {display_name}."
                            if is_hebrew
                            else f"This recipe uses {amount} {unit} of {name}."
                        ),
                        answer_type="ingredient_amount",
                        sources=[result.chunk.id],
                    )
        return None

    def _extract_when_to_add(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        is_hebrew: bool,
    ) -> GroundedAnswer | None:
        match = (_HE_WHEN_ADD_PATTERN if is_hebrew else _WHEN_ADD_PATTERN).match(query)
        if match is None:
            return None

        ingredient_name = match.group("ingredient").strip()
        for result in results:
            if result.chunk.chunk_type != "steps":
                continue
            step_sentences = _parse_step_lines(result.chunk)
            for sentence in step_sentences:
                if not _sentence_mentions_ingredient(sentence, ingredient_name):
                    continue
                together = _extract_companion_ingredients(sentence, ingredient_name)
                section_name = result.chunk.metadata.get("section_name")
                display_ingredient = _format_ingredient_name(ingredient_name, is_hebrew=is_hebrew)
                display_section = _format_section_name(section_name, is_hebrew=is_hebrew)
                display_together = _format_ingredient_list(together, is_hebrew=is_hebrew) if together else None
                ingredient_with_article = _prefix_hebrew_article(display_ingredient) if is_hebrew else display_ingredient
                if isinstance(section_name, str) and together:
                    return GroundedAnswer(
                        answer=(
                            f"מוסיפים את {ingredient_with_article} בחלק של {display_section}, יחד עם {display_together}."
                            if is_hebrew
                            else (
                                f"You add the {ingredient_name} in the {section_name} section, "
                                f"together with {together}."
                            )
                        ),
                        answer_type="when_to_add",
                        sources=[result.chunk.id],
                    )
                if isinstance(section_name, str):
                    return GroundedAnswer(
                        answer=(
                            f"מוסיפים את {ingredient_with_article} בחלק של {display_section}."
                            if is_hebrew
                            else f"You add the {ingredient_name} in the {section_name} section."
                        ),
                        answer_type="when_to_add",
                        sources=[result.chunk.id],
                    )
                return GroundedAnswer(
                    answer=(
                        f"מוסיפים את {ingredient_with_article} בשלב הזה: {sentence}"
                        if is_hebrew
                        else f"You add the {ingredient_name} in this step: {sentence}"
                    ),
                    answer_type="when_to_add",
                    sources=[result.chunk.id],
                )
        return None

    def _extract_section_contents(
        self,
        query: str,
        results: list[RetrievalResult],
        *,
        is_hebrew: bool,
    ) -> GroundedAnswer | None:
        match = None
        patterns = (
            _HE_SECTION_INGREDIENTS_PATTERNS
            if is_hebrew
            else (_SECTION_INGREDIENTS_PATTERN, _SECTION_INGREDIENTS_ALT_PATTERN)
        )
        for pattern in patterns:
            match = pattern.match(query)
            if match is not None:
                break
        if match is None:
            return None

        requested_section = match.group("section").strip().rstrip("?")
        for result in results:
            if result.chunk.chunk_type != "ingredients":
                continue
            section_name = result.chunk.metadata.get("section_name")
            if not isinstance(section_name, str):
                continue
            if not _section_matches(section_name, requested_section):
                continue

            ingredient_names = [
                _format_ingredient_name(name, is_hebrew=is_hebrew)
                for _, _, name in _parse_ingredient_lines(result.chunk)
            ]
            if not ingredient_names:
                continue
            ingredients_text = _join_list(ingredient_names, is_hebrew=is_hebrew)
            display_section = _format_section_name(section_name, is_hebrew=is_hebrew)
            return GroundedAnswer(
                answer=(
                    f"בחלק של {display_section} יש {ingredients_text}."
                    if is_hebrew
                    else f"The {section_name.lower()} section includes {ingredients_text}."
                ),
                answer_type="section_ingredients",
                sources=[result.chunk.id],
            )
        return None

    def _fallback(self, results: list[RetrievalResult], *, is_hebrew: bool) -> GroundedAnswer:
        if not results:
            return GroundedAnswer(
                answer=(
                    "לא מצאתי תשובה מבוססת מתכון לשאלה הזאת."
                    if is_hebrew
                    else "I could not find a grounded recipe answer for that question."
                ),
                answer_type="no_match",
                sources=[],
            )

        top_chunk = results[0].chunk
        section_name = top_chunk.metadata.get("section_name")
        cleaned = _clean_chunk_text(top_chunk)
        if isinstance(section_name, str):
            display_section = _format_section_name(section_name, is_hebrew=is_hebrew)
            answer = (
                f"הערה רלוונטית מחלק {display_section}: {cleaned}"
                if is_hebrew
                else f"Relevant note from the {section_name} section: {cleaned}"
            )
        else:
            answer = f"הערה רלוונטית: {cleaned}" if is_hebrew else f"Relevant note: {cleaned}"
        return GroundedAnswer(
            answer=answer,
            answer_type="fallback_chunk",
            sources=[top_chunk.id],
        )


def _parse_ingredient_lines(chunk: RecipeChunk) -> list[tuple[str, str, str]]:
    parsed: list[tuple[str, str, str]] = []
    for line in chunk.text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:]
        parts = body.split(" ", 2)
        if len(parts) != 3:
            continue
        parsed.append((parts[0], parts[1], parts[2]))
    return parsed


def _parse_step_lines(chunk: RecipeChunk) -> list[str]:
    lines: list[str] = []
    for line in chunk.text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("step "):
            continue
        _, _, sentence = stripped.partition(":")
        sentence = sentence.strip()
        if sentence:
            lines.append(sentence)
    return lines


def _ingredient_matches(candidate: str, requested: str) -> bool:
    candidate_lower = candidate.lower().strip()
    requested_lower = requested.lower().strip()
    candidate_key = catalog.get_ingredient_key(candidate_lower)
    requested_key = catalog.get_ingredient_key(requested_lower)
    if candidate_key is not None and requested_key is not None:
        return candidate_key == requested_key
    return candidate_lower == requested_lower or requested_lower in candidate_lower or candidate_lower in requested_lower


def _sentence_mentions_ingredient(sentence: str, ingredient_name: str) -> bool:
    sentence_lower = sentence.lower()
    if ingredient_name.lower() in sentence_lower:
        return True

    ingredient_key = catalog.get_ingredient_key(ingredient_name)
    if ingredient_key is None:
        return False

    ingredient_data = catalog.get_ingredient_data(ingredient_key) or {}
    aliases = []
    for field in ("aliases_en", "aliases_he"):
        values = ingredient_data.get(field, [])
        if isinstance(values, list):
            aliases.extend([value for value in values if isinstance(value, str)])
    for field in ("display_name_en", "display_name_he"):
        value = ingredient_data.get(field)
        if isinstance(value, str):
            aliases.append(value)
    return any(alias.lower() in sentence_lower for alias in aliases)


def _extract_companion_ingredients(sentence: str, ingredient_name: str) -> str | None:
    lowered = sentence.lower()
    if not lowered.startswith("add "):
        return None

    ingredient_clause = sentence[4:]
    for splitter in (" and simmer", " and cook", " and whisk", " and stir", " until ", "."):
        index = ingredient_clause.lower().find(splitter)
        if index != -1:
            ingredient_clause = ingredient_clause[:index]
            break

    normalized = ingredient_clause.replace(", and ", ", ")
    raw_items = [item.strip() for item in normalized.split(",") if item.strip()]
    cleaned_items: list[str] = []
    for item in raw_items:
        cleaned = re.sub(r"^(the|a|an|and)\s+", "", item, flags=re.IGNORECASE)
        cleaned_items.append(cleaned)

    remaining = [item for item in cleaned_items if not _ingredient_matches(item, ingredient_name)]
    if not remaining:
        return None
    return _join_list(remaining)


def _join_list(items: list[str], *, is_hebrew: bool = False) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} ו{items[1]}" if is_hebrew else f"{items[0]} and {items[1]}"
    return (
        f"{', '.join(items[:-1])} ו{items[-1]}"
        if is_hebrew
        else f"{', '.join(items[:-1])}, and {items[-1]}"
    )


def _format_ingredient_name(name: str, *, is_hebrew: bool) -> str:
    if not is_hebrew:
        return name
    key = catalog.get_ingredient_key(name)
    if key is None:
        return name
    data = catalog.get_ingredient_data(key) or {}
    display_name_he = data.get("display_name_he")
    if isinstance(display_name_he, str) and display_name_he.strip():
        return display_name_he
    return name


def _format_ingredient_list(value: str, *, is_hebrew: bool) -> str:
    if not is_hebrew:
        return value
    items = [item.strip() for item in re.split(r",\s*|\s+and\s+", value) if item.strip()]
    translated = [_format_ingredient_name(item, is_hebrew=True) for item in items]
    return _join_list(translated, is_hebrew=True)


def _format_section_name(section_name: object, *, is_hebrew: bool) -> str:
    if not isinstance(section_name, str):
        return ""
    if not is_hebrew:
        return section_name
    return _SECTION_NAME_TRANSLATIONS.get(section_name, section_name)


def _section_matches(section_name: str, requested_section: str) -> bool:
    section_lower = section_name.lower()
    requested_lower = requested_section.lower()
    if requested_lower in section_lower:
        return True

    translated = _SECTION_NAME_TRANSLATIONS.get(section_name)
    if translated is not None:
        normalized_requested = _normalize_hebrew_section_query(requested_section)
        normalized_translated = _normalize_hebrew_section_query(translated)
        if normalized_requested in normalized_translated or normalized_translated in normalized_requested:
            return True
    return False


def _format_unit(unit: str, amount: str, *, is_hebrew: bool) -> str:
    if not is_hebrew:
        return unit
    translated = _UNIT_TRANSLATIONS.get(unit, unit)
    return translated


def _prefix_hebrew_article(word: str) -> str:
    if not word:
        return word
    if word.startswith("ה"):
        return word
    return f"ה{word}"


def _is_hebrew_text(text: str) -> bool:
    return _HEBREW_CHAR_PATTERN.search(text) is not None


def _normalize_hebrew_section_query(value: str) -> str:
    normalized = value.strip()
    normalized = re.sub(r"^חלק\s+של\s+", "", normalized)
    normalized = re.sub(r"^ה", "", normalized)
    normalized = normalized.replace(" ו", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _clean_chunk_text(chunk: RecipeChunk) -> str:
    lines = [line.strip() for line in chunk.text.splitlines() if line.strip()]
    filtered = [
        line
        for line in lines
        if not line.startswith("Recipe: ")
        and not line.startswith("Section: ")
        and line not in {"Ingredients:", "Instructions:"}
    ]
    text = " ".join(filtered)
    return text[:220].strip()

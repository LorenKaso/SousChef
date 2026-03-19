from __future__ import annotations

import re


_HEBREW_CHAR_PATTERN = re.compile(r"[\u0590-\u05FF]")
_MOJIBAKE_MARKERS = ("×", "Ã", "â")


def repair_text_if_mojibake(text: str) -> str:
    if not text:
        return text
    if _HEBREW_CHAR_PATTERN.search(text):
        return text
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text

    for source_encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired == text:
            continue
        if _HEBREW_CHAR_PATTERN.search(repaired):
            return repaired
        if _mojibake_score(repaired) < _mojibake_score(text):
            return repaired
    return text


def _mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in _MOJIBAKE_MARKERS)

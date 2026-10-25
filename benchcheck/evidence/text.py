"""Text utilities: offset-preserving normalization and sentence/passage splitting.

`normalize` only performs one-character-to-one-character substitutions, so any
span found in the normalized text maps to the identical span of the original
text. Passages shown to users are always sliced from the original text.
"""

from __future__ import annotations

import re

_TRANSLATION = str.maketrans(
    {
        "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
        "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
        "⁺": "+", "⁻": "-", "−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-",
        " ": " ", " ": " ", " ": " ", "µ": "u", "μ": "u", "’": "'", "‘": "'",
    }
)

_ABBREVIATIONS = (
    "e.g.", "i.e.", "et al.", "vs.", "Fig.", "Figs.", "Eq.", "Eqs.", "ca.", "approx.", "Ref.", "Refs.",
    "No.", "cf.", "etc.", "resp.", "Inc.", "Ltd.", "Co.", "Dr.", "Prof.", "St.", "wt.", "al.", "Ex.",
)

_SENTENCE_END = re.compile(r"[.!?](?=\s+[\"'(\[]?[A-Z0-9λ])")
_BLOCK_SPLIT = re.compile(r"\n\s*\n|\n(?=#{1,6}\s)|\n(?=[-*]\s)")


def normalize(text: str) -> str:
    out = text.translate(_TRANSLATION)
    assert len(out) == len(text)
    return out


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def blocks(text: str) -> list[tuple[int, int]]:
    """Paragraph-like blocks (spans) separated by blank lines, headings or list items."""
    spans, start = [], 0
    for m in _BLOCK_SPLIT.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def sentences(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Sentence spans inside text[start:end], protecting common abbreviations and initials."""
    end = len(text) if end is None else end
    spans = []
    cursor = start
    for m in _SENTENCE_END.finditer(text, start, end):
        stop = m.end()
        tail = text[max(start, stop - 8) : stop]
        if any(tail.endswith(a) for a in _ABBREVIATIONS):
            continue
        if re.search(r"(?:^|[\s(])[A-Z]\.$", text[max(start, stop - 3) : stop]):
            continue  # an initial such as "J. Smith"
        spans.append((cursor, stop))
        cursor = stop
    spans.append((cursor, end))
    trimmed = []
    for a, b in spans:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b - a >= 15:
            trimmed.append((a, b))
    return trimmed


def is_verbatim(passage: str, source: str) -> bool:
    """True if the passage occurs in the source text (whitespace-insensitive)."""
    return collapse_ws(passage) in collapse_ws(source)

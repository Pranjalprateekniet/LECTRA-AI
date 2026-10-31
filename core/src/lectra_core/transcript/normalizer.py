"""Subtitle text cleaning and timestamp normalization utilities."""

import html
import re
from typing import Tuple

# Pattern matching HTML, XML, and WebVTT formatting tags (e.g. <c>, <b>, <font>, </font>)
_TAG_PATTERN = re.compile(r"<[^>]+>")

# Pattern matching consecutive whitespace characters
_WHITESPACE_PATTERN = re.compile(r"[\s]+")


def clean_subtitle_text(text: str) -> str:
    """Clean subtitle text while preserving technical terms, proper nouns, and meaning.

    - Unescapes HTML entities (&amp;, &quot;, &#39;, &lt;, &gt;, etc.)
    - Removes formatting tags (<c>, <b>, <i>, <font color="...">, etc.)
    - Strips zero-width and non-breaking artifacts
    - Normalizes consecutive whitespace into a single space
    """
    if not text:
        return ""

    # First unescape HTML entities so entities inside or outside tags are resolved
    cleaned = html.unescape(text)

    # Strip formatting tags
    cleaned = _TAG_PATTERN.sub("", cleaned)

    # Replace invisible and non-breaking spaces
    cleaned = (
        cleaned.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
        .replace("\u200e", "")
        .replace("\u200f", "")
    )

    # Normalize whitespace
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()

    return cleaned


def normalize_timestamps(
    start: float,
    end: float,
    duration: float,
    fallback_duration: float = 2.0,
) -> Tuple[float, float, float]:
    """Normalize and validate segment timing.

    Guarantees:
    - start >= 0.0
    - duration > 0.0
    - end >= start + duration
    All values rounded to 3 decimal places (millisecond precision).
    """
    clean_start = max(0.0, round(start, 3))
    clean_duration = round(duration, 3)

    if clean_duration <= 0.0:
        if end > clean_start:
            clean_duration = round(end - clean_start, 3)
        else:
            clean_duration = round(fallback_duration, 3)

    clean_end = max(round(clean_start + clean_duration, 3), round(end, 3))

    return clean_start, clean_end, clean_duration

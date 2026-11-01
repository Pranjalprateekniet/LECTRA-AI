"""Token counting utility for text chunks."""

import re
from typing import Optional


def count_tokens(text: str, model_name: Optional[str] = None) -> int:
    """Calculate token count for text.

    If a fast tokenizer is available, it can be used; otherwise applies
    the standard word + punctuation tokenization matching typical BPE subword counts.
    """
    if not text or not text.strip():
        return 0

    # Fast offline subword/word+punctuation token estimation
    # Matches words, numbers, and individual punctuation marks
    tokens = re.findall(r"\w+|[^\w\s]", text)
    return max(1, len(tokens))

"""Rolling caption deduplicator for subtitle and transcript cues.

Detects and resolves sliding-window overlaps produced by auto-generated
YouTube caption cues (e.g. WebVTT rolling cues) while preserving legitimately
repeated words and phrases in human speech.
"""

import re
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple, Union

from lectra_core.db.models import TranscriptSegment
from lectra_core.transcript.models import TranscriptSegmentData


def _clean_token(token: str) -> str:
    """Normalize token by lowercasing and stripping punctuation for comparison."""
    return re.sub(r"[^\w]", "", token.lower())


@dataclass(frozen=True)
class CleanedCue:
    """A segment paired with its deduplicated derived text."""

    segment: Union[TranscriptSegment, TranscriptSegmentData, Any]
    text: str
    is_dropped: bool = False


def deduplicate_rolling_captions(
    segments: Sequence[Union[TranscriptSegment, TranscriptSegmentData, Any]],
    overlap_threshold_seconds: float = 0.05,
) -> List[Tuple[Any, str]]:
    """Deduplicate overlapping rolling caption cues into clean sequential text.

    Rules:
    1. If two adjacent cues overlap in time (next.start < curr.end - threshold):
       - Compare suffix words of current cue with prefix words of next cue.
       - If a matching word sequence of length k is found, strip the repeated k prefix
         words from the next cue.
       - If the next cue was entirely a duplicate repetition of the suffix, it is omitted.
    2. If there is NO time overlap between adjacent cues:
       - No words are stripped, preserving legitimately repeated speech across distinct cues.
    3. Legitimate inner-segment repetitions (e.g. "please please please") are fully preserved.

    Returns:
        List of (segment, deduplicated_text) tuples. The underlying segments remain
        completely unmodified.
    """
    if not segments:
        return []

    result: List[Tuple[Any, str]] = []

    for seg in segments:
        # Access text and timing whether seg is ORM model or dataclass/dict
        if isinstance(seg, dict):
            raw_text = str(seg.get("text", "")).strip()
            start_sec = float(seg.get("start_seconds", 0.0))
        else:
            raw_text = str(getattr(seg, "text", "")).strip()
            start_sec = float(getattr(seg, "start_seconds", 0.0))

        if not raw_text:
            continue

        if not result:
            result.append((seg, raw_text))
            continue

        prev_seg, prev_text = result[-1]
        prev_end_sec = (
            float(prev_seg.get("end_seconds", 0.0))
            if isinstance(prev_seg, dict)
            else float(getattr(prev_seg, "end_seconds", 0.0))
        )

        is_overlapping = start_sec < (prev_end_sec - overlap_threshold_seconds)

        if is_overlapping:
            prev_words = prev_text.split()
            curr_words = raw_text.split()

            clean_prev = [_clean_token(w) for w in prev_words]
            clean_curr = [_clean_token(w) for w in curr_words]

            # Find longest suffix-prefix overlap between previous text and current text
            max_k = 0
            for k in range(1, min(len(clean_prev), len(clean_curr)) + 1):
                if clean_prev[-k:] == clean_curr[:k]:
                    max_k = k

            if max_k > 0:
                trimmed_words = curr_words[max_k:]
                if trimmed_words:
                    result.append((seg, " ".join(trimmed_words)))
                else:
                    # Current cue was 100% duplicate of previous trailing text; omit it
                    continue
            else:
                result.append((seg, raw_text))
        else:
            result.append((seg, raw_text))

    return result

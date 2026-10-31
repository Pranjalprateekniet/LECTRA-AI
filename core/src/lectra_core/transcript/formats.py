"""Parsers for YouTube subtitle formats: JSON3, WebVTT, and XML/TTML."""

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Union

from lectra_core.transcript.models import MalformedSubtitleDataError, TranscriptSegmentData
from lectra_core.transcript.normalizer import clean_subtitle_text, normalize_timestamps

_VTT_TIMING_PATTERN = re.compile(
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})"
)


def _parse_vtt_timestamp(hours: Union[str, None], minutes: str, seconds: str, millis: str) -> float:
    h = int(hours) if hours is not None else 0
    m = int(minutes)
    s = int(seconds)
    ms = int(millis)
    return round(h * 3600.0 + m * 60.0 + s + ms / 1000.0, 3)


def parse_json3(
    data: Union[str, Dict[str, Any]],
    language: str,
    source: str,
) -> List[TranscriptSegmentData]:
    """Parse YouTube JSON3 subtitle format into normalized segments."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception as exc:
            raise MalformedSubtitleDataError(f"Failed to parse JSON3 data: {exc}") from exc
    elif isinstance(data, dict):
        parsed = data
    else:
        raise MalformedSubtitleDataError(f"Unsupported JSON3 data type: {type(data)}")

    events = parsed.get("events")
    if events is None or not isinstance(events, list):
        raise MalformedSubtitleDataError("JSON3 data missing 'events' list")

    segments: List[TranscriptSegmentData] = []
    idx = 0

    for event in events:
        if not isinstance(event, dict):
            continue

        raw_segs = event.get("segs")
        if not raw_segs or not isinstance(raw_segs, list):
            continue

        text_parts = [
            seg.get("utf8", "") for seg in raw_segs if isinstance(seg, dict) and "utf8" in seg
        ]
        raw_text = "".join(text_parts)
        cleaned_text = clean_subtitle_text(raw_text)

        if not cleaned_text:
            continue

        start_ms = float(event.get("tStartMs", 0))
        duration_ms = float(event.get("dDurationMs", 0))

        start_sec = start_ms / 1000.0
        dur_sec = duration_ms / 1000.0
        end_sec = start_sec + dur_sec

        start_sec, end_sec, dur_sec = normalize_timestamps(start_sec, end_sec, dur_sec)

        segments.append(
            TranscriptSegmentData(
                segment_index=idx,
                start_seconds=start_sec,
                end_seconds=end_sec,
                duration_seconds=dur_sec,
                text=cleaned_text,
                language=language,
                source=source,
            )
        )
        idx += 1

    return segments


def parse_vtt(
    content: str,
    language: str,
    source: str,
) -> List[TranscriptSegmentData]:
    """Parse WebVTT subtitle format into normalized segments."""
    if not isinstance(content, str):
        raise MalformedSubtitleDataError("VTT content must be a string")

    lines = content.splitlines()
    segments: List[TranscriptSegmentData] = []
    idx = 0

    i = 0
    num_lines = len(lines)

    while i < num_lines:
        line = lines[i].strip()
        match = _VTT_TIMING_PATTERN.search(line)
        if match:
            start_h, start_m, start_s, start_ms, end_h, end_m, end_s, end_ms = match.groups()
            start_sec = _parse_vtt_timestamp(start_h, start_m, start_s, start_ms)
            end_sec = _parse_vtt_timestamp(end_h, end_m, end_s, end_ms)
            dur_sec = max(0.1, round(end_sec - start_sec, 3))

            # Consume following cue text lines until empty line
            i += 1
            text_lines = []
            while i < num_lines and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1

            raw_text = " ".join(text_lines)
            cleaned_text = clean_subtitle_text(raw_text)

            if cleaned_text:
                start_sec, end_sec, dur_sec = normalize_timestamps(start_sec, end_sec, dur_sec)
                segments.append(
                    TranscriptSegmentData(
                        segment_index=idx,
                        start_seconds=start_sec,
                        end_seconds=end_sec,
                        duration_seconds=dur_sec,
                        text=cleaned_text,
                        language=language,
                        source=source,
                    )
                )
                idx += 1
        else:
            i += 1

    return segments


def parse_xml(
    content: str,
    language: str,
    source: str,
) -> List[TranscriptSegmentData]:
    """Parse YouTube XML / TTML / srv1 / srv2 subtitle format into normalized segments."""
    if not isinstance(content, str):
        raise MalformedSubtitleDataError("XML content must be a string")

    try:
        root = ET.fromstring(content)
    except Exception as exc:
        raise MalformedSubtitleDataError(f"Failed to parse subtitle XML: {exc}") from exc

    segments: List[TranscriptSegmentData] = []
    idx = 0

    # Search for <text start="..." dur="..."> or <p t="..." d="...">
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]  # Strip XML namespace if present
        raw_text = "".join(elem.itertext())
        cleaned_text = clean_subtitle_text(raw_text)

        if not cleaned_text:
            continue

        if tag == "text":
            try:
                start_sec = float(elem.attrib.get("start", 0.0))
                dur_sec = float(elem.attrib.get("dur", 0.0))
            except (ValueError, TypeError):
                continue
            end_sec = start_sec + dur_sec
            start_sec, end_sec, dur_sec = normalize_timestamps(start_sec, end_sec, dur_sec)

            segments.append(
                TranscriptSegmentData(
                    segment_index=idx,
                    start_seconds=start_sec,
                    end_seconds=end_sec,
                    duration_seconds=dur_sec,
                    text=cleaned_text,
                    language=language,
                    source=source,
                )
            )
            idx += 1

        elif tag == "p" and ("t" in elem.attrib or "begin" in elem.attrib):
            if "t" in elem.attrib:
                try:
                    start_sec = float(elem.attrib["t"]) / 1000.0
                    dur_sec = float(elem.attrib.get("d", 0.0)) / 1000.0
                except (ValueError, TypeError):
                    continue
                end_sec = start_sec + dur_sec
            else:
                continue

            start_sec, end_sec, dur_sec = normalize_timestamps(start_sec, end_sec, dur_sec)
            segments.append(
                TranscriptSegmentData(
                    segment_index=idx,
                    start_seconds=start_sec,
                    end_seconds=end_sec,
                    duration_seconds=dur_sec,
                    text=cleaned_text,
                    language=language,
                    source=source,
                )
            )
            idx += 1

    return segments


def parse_subtitle_content(
    content: Union[str, Dict[str, Any]],
    format_name: str,
    language: str,
    source: str,
) -> List[TranscriptSegmentData]:
    """Dispatch to the appropriate format parser based on format_name or payload."""
    fmt = (format_name or "").lower().strip()

    if isinstance(content, dict) or fmt == "json3":
        return parse_json3(content, language, source)

    if fmt in ("vtt", "webvtt"):
        return parse_vtt(str(content), language, source)

    if fmt in ("srv1", "srv2", "srv3", "ttml", "xml"):
        return parse_xml(str(content), language, source)

    # Heuristic detection if format name is generic or unknown
    if isinstance(content, str):
        trimmed = content.strip()
        if trimmed.startswith("{"):
            return parse_json3(trimmed, language, source)
        if "WEBVTT" in trimmed[:50] or "-->" in trimmed[:200]:
            return parse_vtt(trimmed, language, source)
        if trimmed.startswith("<") or "</" in trimmed:
            return parse_xml(trimmed, language, source)

    raise MalformedSubtitleDataError(f"Unsupported subtitle format: '{format_name}'")

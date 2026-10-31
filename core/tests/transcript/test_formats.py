"""Unit tests for subtitle format parsers and text normalization."""

import pytest
from lectra_core.transcript.formats import (
    parse_json3,
    parse_subtitle_content,
    parse_vtt,
    parse_xml,
)
from lectra_core.transcript.models import MalformedSubtitleDataError
from lectra_core.transcript.normalizer import clean_subtitle_text, normalize_timestamps

from .mock_extractor import (
    SAMPLE_JSON3_ENGLISH,
    SAMPLE_JSON3_HINDI,
    SAMPLE_VTT_ENGLISH,
    SAMPLE_XML_ENGLISH,
)


def test_clean_subtitle_text_html_entities_and_tags():
    raw = "<b>Hello &amp; welcome</b> to &quot;Revision RAG&#39;s&quot; <c.color>class</c>!"
    cleaned = clean_subtitle_text(raw)
    assert cleaned == 'Hello & welcome to "Revision RAG\'s" class!'


def test_clean_subtitle_text_whitespace_and_zero_width():
    raw = "  Line 1\n\n\t  Line   2 \u200b with \xa0 non-breaking   spaces.  "
    cleaned = clean_subtitle_text(raw)
    assert cleaned == "Line 1 Line 2 with non-breaking spaces."


def test_clean_subtitle_text_empty_and_tags_only():
    assert clean_subtitle_text("") == ""
    assert clean_subtitle_text("<font color='#000'></font>") == ""
    assert clean_subtitle_text("   \n\t  ") == ""


def test_normalize_timestamps():
    # Regular valid timestamps
    s, e, d = normalize_timestamps(1.2345, 4.5678, 3.3333)
    assert s == 1.234
    assert e == 4.568
    assert d == 3.333

    # Negative start clamped to 0.0
    s, e, d = normalize_timestamps(-2.0, 3.0, 5.0)
    assert s == 0.0
    assert e == 5.0
    assert d == 5.0

    # Missing duration with end time
    s, e, d = normalize_timestamps(2.0, 5.5, 0.0)
    assert s == 2.0
    assert d == 3.5
    assert e == 5.5

    # Missing duration and end <= start
    s, e, d = normalize_timestamps(3.0, 3.0, 0.0, fallback_duration=2.0)
    assert s == 3.0
    assert d == 2.0
    assert e == 5.0


def test_parse_json3_english():
    segments = parse_json3(SAMPLE_JSON3_ENGLISH, language="en", source="manual")
    assert len(segments) == 3

    assert segments[0].segment_index == 0
    assert segments[0].start_seconds == 0.0
    assert segments[0].end_seconds == 2.5
    assert segments[0].duration_seconds == 2.5
    assert segments[0].text == "Hello & welcome to the course."
    assert segments[0].language == "en"
    assert segments[0].source == "manual"

    assert segments[1].segment_index == 1
    assert segments[1].start_seconds == 2.5
    assert segments[1].end_seconds == 5.6
    assert segments[1].duration_seconds == 3.1
    # Check that <b> tag was removed and newline was trimmed
    assert segments[1].text == "Today we will study binary search."

    assert segments[2].segment_index == 2
    assert segments[2].start_seconds == 5.6
    assert segments[2].end_seconds == 7.6
    assert segments[2].duration_seconds == 2.0
    assert "Let's start with time complexity: O(log N)." in segments[2].text


def test_parse_json3_hindi_preserves_language_and_script():
    segments = parse_json3(SAMPLE_JSON3_HINDI, language="hi", source="generated")
    assert len(segments) == 2

    assert segments[0].language == "hi"
    assert segments[0].source == "generated"
    assert segments[0].start_seconds == 1.0
    assert segments[0].end_seconds == 4.0
    assert "नमस्ते दोस्तों" in segments[0].text

    assert segments[1].language == "hi"
    assert segments[1].start_seconds == 4.0
    assert segments[1].end_seconds == 6.5
    assert "महत्वपूर्ण विषय है" in segments[1].text


def test_parse_vtt_english():
    segments = parse_vtt(SAMPLE_VTT_ENGLISH, language="en", source="manual")
    assert len(segments) == 3

    assert segments[0].segment_index == 0
    assert segments[0].start_seconds == 1.0
    assert segments[0].end_seconds == 3.5
    assert segments[0].text == "Hello & welcome to the revision session."

    assert segments[1].segment_index == 1
    assert segments[1].start_seconds == 3.5
    assert segments[1].end_seconds == 6.8
    assert segments[1].text == "Today we discuss dynamic programming."

    assert segments[2].segment_index == 2
    assert segments[2].start_seconds == 7.0
    assert segments[2].end_seconds == 10.0
    assert segments[2].text == "Remember to review memoization."


def test_parse_xml_english():
    segments = parse_xml(SAMPLE_XML_ENGLISH, language="en", source="manual")
    assert len(segments) == 2

    assert segments[0].segment_index == 0
    assert segments[0].start_seconds == 1.5
    assert segments[0].end_seconds == 4.0
    assert segments[0].text == 'Welcome to the "lecture"'

    assert segments[1].segment_index == 1
    assert segments[1].start_seconds == 4.0
    assert segments[1].end_seconds == 7.0
    assert segments[1].text == "We are learning Python & algorithms"


def test_parse_subtitle_content_dispatch():
    # Dispatch JSON3
    res1 = parse_subtitle_content(SAMPLE_JSON3_ENGLISH, "json3", "en", "manual")
    assert len(res1) == 3

    # Dispatch VTT
    res2 = parse_subtitle_content(SAMPLE_VTT_ENGLISH, "vtt", "en", "manual")
    assert len(res2) == 3

    # Dispatch XML
    res3 = parse_subtitle_content(SAMPLE_XML_ENGLISH, "srv1", "en", "manual")
    assert len(res3) == 2


def test_parse_malformed_json_raises():
    with pytest.raises(MalformedSubtitleDataError):
        parse_json3("not-a-valid-json", language="en", source="manual")

    with pytest.raises(MalformedSubtitleDataError):
        parse_json3({"invalid_key": "no_events"}, language="en", source="manual")


def test_parse_malformed_xml_raises():
    with pytest.raises(MalformedSubtitleDataError):
        parse_xml("<unclosed_tag", language="en", source="manual")

"""Offline translation service powered by Argos Translate.

Translates supported non-English transcript segments into English while
strictly preserving segment timestamps, sequence indices, and audio/source alignment.
"""

import os
from pathlib import Path
from typing import Any, List, Optional

from lectra_core.config import Settings, get_settings
from lectra_core.logging import get_logger
from lectra_core.transcript.models import TranscriptSegmentData

logger = get_logger("lectra.translation.service")


class UnsupportedLanguageError(Exception):
    """Raised when transcript language cannot be translated to English by configured models."""

    def __init__(self, language: str):
        self.language = language
        super().__init__(f"Language '{language}' is not supported for translation to English.")


def _configure_offline_argos_environment(packages_dir: Path) -> None:
    """Ensure Argos Translate and Stanza operate strictly offline in sandbox environments."""
    resolved_dir = str(packages_dir.resolve())
    if "ARGOS_PACKAGES_DIR" not in os.environ or not os.environ["ARGOS_PACKAGES_DIR"]:
        os.environ["ARGOS_PACKAGES_DIR"] = resolved_dir

    # Guard XDG directories to ensure writable cache locations
    os.environ.setdefault("XDG_DATA_HOME", "/tmp/argos_data")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/argos_cache")
    os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/argos_config")

    # Patch Stanza sentence boundary detection to reuse local resources without network calls
    try:
        import stanza
        import stanza.pipeline.core

        original_stanza_init = stanza.Pipeline.__init__

        def _patched_stanza_init(self: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs["download_method"] = stanza.pipeline.core.DownloadMethod.REUSE_RESOURCES
            return original_stanza_init(self, *args, **kwargs)

        stanza.Pipeline.__init__ = _patched_stanza_init
    except (ImportError, AttributeError):
        pass


class TranslationService:
    """Manages translation of non-English transcript text and segments into English."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        _configure_offline_argos_environment(self.settings.argos_packages_dir)
        self._languages_cache: Optional[List[Any]] = None

    def _get_installed_languages(self) -> List[Any]:
        """Load and cache installed Argos languages."""
        if self._languages_cache is None:
            try:
                import argostranslate.translate

                self._languages_cache = argostranslate.translate.get_installed_languages()
            except Exception as exc:
                logger.warning(f"Could not load installed Argos languages: {exc}")
                self._languages_cache = []
        return self._languages_cache

    def normalize_lang_code(self, lang_code: str) -> str:
        """Extract primary language subtag (e.g., 'hi-Latn' -> 'hi', 'en-US' -> 'en')."""
        clean = (lang_code or "").strip().lower()
        if "-" in clean:
            clean = clean.split("-")[0]
        if "." in clean:
            clean = clean.split(".")[0]
        return clean

    def is_language_supported(self, lang_code: str) -> bool:
        """Check if translation from lang_code to English is supported."""
        normalized = self.normalize_lang_code(lang_code)
        if normalized == "en":
            return True

        installed = self._get_installed_languages()
        from_lang = next((lang for lang in installed if lang.code == normalized), None)
        to_lang = next((lang for lang in installed if lang.code == "en"), None)

        if from_lang and to_lang:
            trans = from_lang.get_translation(to_lang)
            return trans is not None
        return False

    def translate_text(self, text: str, source_lang: str) -> str:
        """Translate a single string into English."""
        normalized = self.normalize_lang_code(source_lang)
        if normalized == "en" or not text.strip():
            return text

        installed = self._get_installed_languages()
        from_lang = next((lang for lang in installed if lang.code == normalized), None)
        to_lang = next((lang for lang in installed if lang.code == "en"), None)

        if not from_lang or not to_lang:
            raise UnsupportedLanguageError(source_lang)

        translation = from_lang.get_translation(to_lang)
        if not translation:
            raise UnsupportedLanguageError(source_lang)

        try:
            return translation.translate(text)
        except Exception as exc:
            logger.error(
                "Argos translation error",
                extra={"source_lang": source_lang, "error": str(exc)},
            )
            raise

    def translate_segments(
        self,
        segments: List[TranscriptSegmentData],
        source_lang: str,
    ) -> List[TranscriptSegmentData]:
        """Translate a list of transcript segments to English preserving timing and order."""
        normalized = self.normalize_lang_code(source_lang)
        if normalized == "en":
            return list(segments)

        if not self.is_language_supported(source_lang):
            raise UnsupportedLanguageError(source_lang)

        installed = self._get_installed_languages()
        from_lang = next((lang for lang in installed if lang.code == normalized), None)
        to_lang = next((lang for lang in installed if lang.code == "en"), None)

        if not from_lang or not to_lang:
            raise UnsupportedLanguageError(source_lang)

        translation = from_lang.get_translation(to_lang)
        if not translation:
            raise UnsupportedLanguageError(source_lang)

        translated_segments: List[TranscriptSegmentData] = []
        for seg in segments:
            raw_text = seg.text or ""
            if raw_text.strip():
                try:
                    translated_text = translation.translate(raw_text)
                except Exception as exc:
                    logger.warning(
                        "Segment translation failure; keeping original segment text",
                        extra={"segment_index": seg.segment_index, "error": str(exc)},
                    )
                    translated_text = raw_text
            else:
                translated_text = raw_text

            translated_segments.append(
                TranscriptSegmentData(
                    segment_index=seg.segment_index,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                    duration_seconds=seg.duration_seconds,
                    text=translated_text,
                    language="en",
                    source=seg.source,
                )
            )

        logger.info(
            "Translated transcript segments into English",
            extra={
                "source_language": source_lang,
                "segments_count": len(translated_segments),
            },
        )
        return translated_segments

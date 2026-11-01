"""Reusable Groq API client with error mapping and credential protection."""

from typing import Any, List, Optional

import groq

from lectra_core.config import Settings, get_settings
from lectra_core.generation.exceptions import (
    GenerationError,
    GroqAuthError,
    GroqClientError,
    GroqModelUnavailableError,
    GroqRateLimitError,
    GroqTimeoutError,
)
from lectra_core.logging import get_logger

logger = get_logger("lectra.generation.groq_client")


class GroqClient:
    """Manages reusable Groq SDK client instance and handles API errors safely."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[groq.Groq] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._api_key = self.settings.groq_api_key

    def _get_client(self) -> groq.Groq:
        """Lazily initialize or retrieve the cached Groq client instance."""
        if self._client is not None:
            return self._client

        if not self._api_key or not self._api_key.strip():
            raise GroqAuthError("GROQ_API_KEY is not configured in application settings.")

        self._client = groq.Groq(
            api_key=self._api_key.strip(),
            timeout=self.settings.groq_timeout_seconds,
        )
        return self._client

    def generate_chat_completion(
        self,
        messages: List[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        """Call Groq chat completions with timeout, JSON formatting, and error mapping."""
        client = self._get_client()
        target_model = model or self.settings.groq_model_name
        temp = temperature if temperature is not None else self.settings.groq_temperature
        fmt = response_format or {"type": "json_object"}

        logger.info(
            "Calling Groq chat completions",
            extra={
                "model": target_model,
                "temperature": temp,
                "message_count": len(messages),
            },
        )

        try:
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=target_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temp,
                response_format=fmt,  # type: ignore[arg-type]
                timeout=self.settings.groq_timeout_seconds,
            )

            if not response.choices:
                raise GroqClientError("Groq returned an empty choice list with no completions.")

            choice = response.choices[0]
            content = choice.message.content or ""

            # Ensure internal reasoning (if produced by reasoning models) is never exposed
            return content.strip()

        except groq.AuthenticationError as exc:
            logger.error("Groq authentication failed: invalid credentials")
            raise GroqAuthError(
                "Authentication failed with Groq. Please verify GROQ_API_KEY."
            ) from exc

        except groq.NotFoundError as exc:
            logger.error("Groq model not found or unavailable", extra={"model": target_model})
            raise GroqModelUnavailableError(
                f"Configured model '{target_model}' is not available to this Groq account."
            ) from exc

        except groq.RateLimitError as exc:
            logger.warning("Groq rate limit encountered")
            raise GroqRateLimitError(
                "Groq API rate limit or quota exceeded. Please retry later."
            ) from exc

        except groq.APITimeoutError as exc:
            logger.error(
                "Groq API request timed out", extra={"timeout": self.settings.groq_timeout_seconds}
            )
            raise GroqTimeoutError(
                f"Groq API call timed out after {self.settings.groq_timeout_seconds} seconds."
            ) from exc

        except groq.APIConnectionError as exc:
            logger.error("Groq API connection failure")
            raise GroqClientError(
                "Failed to connect to Groq API. Please check network connectivity."
            ) from exc

        except groq.GroqError as exc:
            logger.error("Groq API error encountered")
            raise GroqClientError(f"Groq provider error: {exc.__class__.__name__}") from exc

        except GenerationError:
            raise

        except Exception as exc:
            logger.error("Unexpected error invoking Groq API")
            raise GroqClientError("An unexpected error occurred communicating with Groq.") from exc

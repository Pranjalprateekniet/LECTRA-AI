"""Unit tests for GroqClient error mapping, authentication, and response handling."""

from unittest.mock import MagicMock

import groq
import pytest
from lectra_core.config import Settings
from lectra_core.generation.exceptions import (
    GroqAuthError,
    GroqClientError,
    GroqModelUnavailableError,
    GroqRateLimitError,
    GroqTimeoutError,
)
from lectra_core.generation.groq_client import GroqClient


def test_missing_api_key_raises_auth_error():
    """Verify that absent or empty GROQ_API_KEY raises GroqAuthError."""
    settings = Settings(groq_api_key=None)
    client = GroqClient(settings=settings)
    with pytest.raises(GroqAuthError, match="GROQ_API_KEY is not configured"):
        client.generate_chat_completion([{"role": "user", "content": "hi"}])


def test_reusable_client_instance():
    """Verify that multiple calls reuse the cached Groq client instance."""
    mock_sdk_client = MagicMock()
    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    c1 = client._get_client()
    c2 = client._get_client()
    assert c1 is c2
    assert c1 is mock_sdk_client


def test_successful_chat_completion():
    """Verify successful response extraction from choice message content."""
    mock_sdk_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"status": "answered", "answer": "Optimal choice"}'
    mock_choice.message.reasoning = "Internal chain of thought"
    mock_sdk_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    result = client.generate_chat_completion([{"role": "user", "content": "test"}])

    assert result == '{"status": "answered", "answer": "Optimal choice"}'
    # Reasoning should not be part of result
    assert "Internal chain of thought" not in result


def test_authentication_error_mapping():
    """Verify groq.AuthenticationError maps to GroqAuthError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = groq.AuthenticationError(
        message="Invalid API Key",
        response=MagicMock(status_code=401),
        body={"error": {"message": "Invalid API Key"}},
    )

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    with pytest.raises(GroqAuthError, match="Authentication failed with Groq"):
        client.generate_chat_completion([{"role": "user", "content": "test"}])


def test_model_not_found_mapping():
    """Verify groq.NotFoundError maps to GroqModelUnavailableError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = groq.NotFoundError(
        message="Model not found",
        response=MagicMock(status_code=404),
        body={"error": {"message": "The model `openai/gpt-oss-120b` does not exist"}},
    )

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    with pytest.raises(GroqModelUnavailableError, match="not available to this Groq account"):
        client.generate_chat_completion([{"role": "user", "content": "test"}])


def test_rate_limit_error_mapping():
    """Verify groq.RateLimitError maps to GroqRateLimitError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = groq.RateLimitError(
        message="Rate limit reached",
        response=MagicMock(status_code=429),
        body={"error": {"message": "Rate limit exceeded"}},
    )

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    with pytest.raises(GroqRateLimitError, match="rate limit or quota exceeded"):
        client.generate_chat_completion([{"role": "user", "content": "test"}])


def test_timeout_error_mapping():
    """Verify groq.APITimeoutError maps to GroqTimeoutError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = groq.APITimeoutError(request=MagicMock())

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    with pytest.raises(GroqTimeoutError, match="timed out"):
        client.generate_chat_completion([{"role": "user", "content": "test"}])


def test_empty_choices_raises_client_error():
    """Verify that an empty choices list raises GroqClientError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = MagicMock(choices=[])

    client = GroqClient(settings=Settings(groq_api_key="gsk_test"), client=mock_sdk_client)
    with pytest.raises(GroqClientError, match="empty choice list"):
        client.generate_chat_completion([{"role": "user", "content": "test"}])

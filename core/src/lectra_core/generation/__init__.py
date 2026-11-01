"""Grounded RAG Answer Generation module using Groq + GPT-OSS-120B."""

from lectra_core.generation.context_builder import ContextBuilder, ContextBuildResult
from lectra_core.generation.exceptions import (
    CitationValidationError,
    ContextBudgetExceededError,
    GenerationError,
    GroqAuthError,
    GroqClientError,
    GroqModelUnavailableError,
    GroqRateLimitError,
    GroqTimeoutError,
)
from lectra_core.generation.groq_client import GroqClient
from lectra_core.generation.prompts import SYSTEM_PROMPT_V1, USER_PROMPT_TEMPLATE
from lectra_core.generation.schemas import (
    AnswerResponse,
    AnswerStatus,
    CitationItem,
    GenerationRequest,
    LLMRawAnswer,
)
from lectra_core.generation.service import GenerationService

__all__ = [
    "AnswerResponse",
    "AnswerStatus",
    "CitationItem",
    "CitationValidationError",
    "ContextBuildResult",
    "ContextBuilder",
    "ContextBudgetExceededError",
    "GenerationError",
    "GenerationRequest",
    "GroqAuthError",
    "GroqClientError",
    "GroqModelUnavailableError",
    "GroqRateLimitError",
    "GroqTimeoutError",
    "GroqClient",
    "LLMRawAnswer",
    "GenerationService",
    "SYSTEM_PROMPT_V1",
    "USER_PROMPT_TEMPLATE",
]

"""Domain exceptions for LLM answer generation and Groq client integration."""


class GenerationError(Exception):
    """Base exception for all answer generation pipeline errors."""


class GroqClientError(GenerationError):
    """Raised when Groq API encounters an unexpected error."""


class GroqAuthError(GroqClientError):
    """Raised when authentication with Groq fails due to missing or invalid credentials."""


class GroqModelUnavailableError(GroqClientError):
    """Raised when the requested Groq model is inaccessible or decommissioned."""


class GroqRateLimitError(GroqClientError):
    """Raised when Groq API rate limits or quota thresholds are exceeded."""


class GroqTimeoutError(GroqClientError):
    """Raised when Groq API request times out."""


class ContextBudgetExceededError(GenerationError):
    """Raised when context and query tokens exceed the configured context window budget."""


class CitationValidationError(GenerationError):
    """Raised when citation references cannot be validated against supplied source chunks."""

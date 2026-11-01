"""FastAPI endpoints for grounded RAG answer generation."""

from fastapi import APIRouter, Depends, HTTPException, status
from lectra_backend.dependencies import get_generation_service
from lectra_core.generation.exceptions import (
    ContextBudgetExceededError,
    GenerationError,
    GroqAuthError,
    GroqClientError,
    GroqModelUnavailableError,
    GroqRateLimitError,
    GroqTimeoutError,
)
from lectra_core.generation.schemas import AnswerResponse, GenerationRequest
from lectra_core.generation.service import GenerationService
from lectra_core.logging import get_logger

logger = get_logger("lectra.backend.api.answers")

router = APIRouter(prefix="/answers", tags=["answers"])


@router.post(
    "/generate",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate grounded revision answer with timestamped YouTube citations",
)
def generate_answer(
    request: GenerationRequest,
    service: GenerationService = Depends(get_generation_service),
) -> AnswerResponse:
    """Accept student question, retrieve context, and generate grounded answer with citations."""
    try:
        return service.generate_answer(request)

    except ValueError as exc:
        logger.warning("Invalid answer generation request", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except ContextBudgetExceededError as exc:
        logger.warning("Context budget exceeded for generation request", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The question or prompt is too large to fit within the model context budget.",
        ) from exc

    except GroqAuthError as exc:
        logger.error("LLM authentication failure", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service currently unavailable. Please verify provider credentials.",
        ) from exc

    except GroqRateLimitError as exc:
        logger.warning("LLM provider rate limit encountered", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM provider rate limit exceeded. Please retry in a few moments.",
        ) from exc

    except GroqTimeoutError as exc:
        logger.error("LLM provider request timed out", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider timed out while generating the answer.",
        ) from exc

    except GroqModelUnavailableError as exc:
        logger.error("Configured LLM model is unavailable", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured LLM model is currently unavailable on the provider.",
        ) from exc

    except GroqClientError as exc:
        logger.error("LLM client communication failure", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="An error occurred communicating with the LLM provider.",
        ) from exc

    except GenerationError as exc:
        logger.error("RAG generation pipeline error", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate grounded answer from retrieved context.",
        ) from exc

    except Exception as exc:
        logger.error("Unexpected error in answer generation endpoint", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during answer generation.",
        ) from exc

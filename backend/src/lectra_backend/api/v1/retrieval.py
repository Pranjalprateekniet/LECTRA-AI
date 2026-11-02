"""Retrieval API endpoints for semantic similarity search."""

from fastapi import APIRouter, Depends, HTTPException, status
from lectra_backend.dependencies import get_retrieval_service
from lectra_core.logging import get_logger
from lectra_core.retrieval.remote import RemoteRetrievalService
from lectra_core.retrieval.schemas import RetrievalQuery, SearchResponse
from lectra_core.retrieval.service import RetrievalError, RetrievalService

logger = get_logger("lectra.backend.api.retrieval")

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic similarity search over indexed video transcript chunks",
)
def search_chunks(
    request: RetrievalQuery,
    service: RetrievalService | RemoteRetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    """Accept natural-language query and return relevant transcript chunks with source citations."""
    try:
        return service.search_query(request)
    except ValueError as exc:
        logger.warning("Invalid retrieval request", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RetrievalError as exc:
        logger.error("Vector retrieval service failure", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval service currently unavailable. Please verify vector store.",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error during semantic search", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during search processing.",
        ) from exc

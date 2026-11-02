"""FastAPI request dependencies."""

from collections.abc import Generator

from fastapi import Depends
from lectra_core.config import Settings, get_settings
from lectra_core.db.session import get_db
from lectra_core.generation.service import GenerationService
from lectra_core.retrieval.remote import RemoteRetrievalService
from lectra_core.retrieval.service import RetrievalService
from sqlalchemy.orm import Session


def get_db_session(settings: Settings = Depends(get_settings)) -> Generator[Session, None, None]:
    """Provide a database session dependency bound to active application settings."""
    yield from get_db(settings)


def get_retrieval_service(
    settings: Settings = Depends(get_settings),
) -> RetrievalService | RemoteRetrievalService:
    """Provide a retrieval service instance bound to active settings.

    In USER mode, defaults directly to local RetrievalService against local persistent Qdrant.
    If RETRIEVAL_API_URL is explicitly configured, RemoteRetrievalService is used.
    """
    if settings.retrieval_api_url:
        return RemoteRetrievalService(settings=settings)
    return RetrievalService(settings=settings)


def get_generation_service(
    settings: Settings = Depends(get_settings),
    retrieval_service: RetrievalService | RemoteRetrievalService = Depends(get_retrieval_service),
) -> GenerationService:
    """Provide a generation service instance bound to active settings."""
    return GenerationService(settings=settings, retrieval_service=retrieval_service)

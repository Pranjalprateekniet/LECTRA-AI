"""FastAPI request dependencies."""

from collections.abc import Generator

from fastapi import Depends
from lectra_core.config import Settings, get_settings
from lectra_core.db.session import get_db
from lectra_core.retrieval.service import RetrievalService
from sqlalchemy.orm import Session


def get_db_session(settings: Settings = Depends(get_settings)) -> Generator[Session, None, None]:
    """Provide a database session dependency bound to active application settings."""
    yield from get_db(settings)


def get_retrieval_service(
    settings: Settings = Depends(get_settings),
) -> RetrievalService:
    """Provide a retrieval service instance bound to active settings."""
    return RetrievalService(settings=settings)

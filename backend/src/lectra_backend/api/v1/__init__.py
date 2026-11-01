"""API v1 router configuration."""

from fastapi import APIRouter
from lectra_backend.api.v1.health import router as health_router
from lectra_backend.api.v1.jobs import router as jobs_router
from lectra_backend.api.v1.playlists import router as playlists_router
from lectra_backend.api.v1.retrieval import router as retrieval_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(playlists_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(retrieval_router)

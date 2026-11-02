"""FastAPI entry point for the hosted read-only retrieval service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from retrieval_service import __version__
from retrieval_service.config import RetrievalServiceSettings, get_service_settings
from retrieval_service.limiter import (
    BaseRateLimiter,
    create_rate_limiter,
    get_client_ip,
)
from retrieval_service.schemas import (
    HealthCheckResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from retrieval_service.service import (
    HostedRetrievalError,
    HostedRetrievalService,
    HostedRetrievalUnavailableError,
)

logger = logging.getLogger("retrieval_service")


def create_app(
    settings: Optional[RetrievalServiceSettings] = None,
    rate_limiter: Optional[BaseRateLimiter] = None,
    retrieval_service: Optional[HostedRetrievalService] = None,
) -> FastAPI:
    """Application factory for the hosted retrieval API."""
    cfg = settings or get_service_settings()

    # Configure root logger format and level
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    limiter = rate_limiter or create_rate_limiter(
        redis_url=cfg.redis_url,
        rate_limit_per_minute=cfg.rate_limit_per_minute,
        rate_limit_per_hour=cfg.rate_limit_per_hour,
    )

    service = retrieval_service or HostedRetrievalService(settings=cfg)
    concurrency_semaphore = asyncio.Semaphore(cfg.max_concurrent_requests)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        logger.info(
            "Hosted Retrieval Service starting up",
            extra={
                "environment": cfg.environment,
                "embedding_model": cfg.embedding_model_name,
                "collection": cfg.qdrant_collection_name,
                "redis_configured": bool(cfg.redis_url),
            },
        )
        # Preload and cache embedding model weights once at startup
        service.warmup()
        yield
        logger.info("Hosted Retrieval Service shutting down")
        service.close()

    app = FastAPI(
        title="Revision RAG Hosted Retrieval API",
        description="Public, read-only semantic retrieval API for Revision RAG knowledge bases",
        version=__version__,
        lifespan=lifespan,
    )

    # Store components in app state for access/testing
    app.state.settings = cfg
    app.state.limiter = limiter
    app.state.service = service
    app.state.concurrency_semaphore = concurrency_semaphore

    # CORS configuration - only enable if explicit origins are configured.
    # The primary workflow is server-to-server HTTP POST requests.
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    # Error Handlers: Prevent leaking internal stack traces or database info
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "Invalid request validation",
            extra={"client_ip": get_client_ip(request, cfg.trusted_proxies)},
        )
        # Format errors into clean, json-serializable structures
        clean_errors = [
            {"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid request parameters.", "errors": clean_errors},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled server exception", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred during request processing."},
        )

    @app.get("/", summary="Service information")
    def root():
        return {
            "name": "Revision RAG Hosted Retrieval API",
            "version": __version__,
            "status": "operational",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get(
        "/health",
        response_model=HealthCheckResponse,
        summary="Service operational health check",
    )
    def health_check(response: Response):
        """Verify vector store connectivity without exposing credentials or internal topology."""
        health = service.check_health()
        is_healthy = health.get("healthy", False)
        qdrant_status = str(health.get("qdrant_status", "unknown"))

        payload = {
            "status": "healthy" if is_healthy else "degraded",
            "qdrant_status": qdrant_status,
            "embedding_model": cfg.embedding_model_name,
            "version": __version__,
        }

        if not is_healthy:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return payload

    @app.post(
        "/api/v1/retrieve",
        response_model=RetrieveResponse,
        status_code=status.HTTP_200_OK,
        summary="Public read-only semantic retrieval endpoint",
    )
    async def retrieve(
        request: Request,
        body: RetrieveRequest,
    ) -> JSONResponse:
        """Search relevant lecture transcript chunks with timestamp citations."""
        client_ip = get_client_ip(request, cfg.trusted_proxies)

        # 1. IP Rate Limiting Check
        rl_res = limiter.check_rate_limit(client_ip)
        if not rl_res.allowed:
            logger.warning(
                "Client rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "retry_after": rl_res.retry_after_seconds,
                    "minute_limit": rl_res.limit_minute,
                    "hour_limit": rl_res.limit_hour,
                },
            )
            msg = f"Rate limit exceeded. Please retry after {rl_res.retry_after_seconds} seconds."
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": msg},
                headers=rl_res.headers,
            )

        # 2. Concurrency limiting to prevent model/memory starvation
        try:
            # Try acquiring concurrency slot with short timeout
            await asyncio.wait_for(concurrency_semaphore.acquire(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning(
                "Server concurrency limit saturated",
                extra={"client_ip": client_ip, "limit": cfg.max_concurrent_requests},
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "Server is currently at capacity. Please retry in a few moments."
                },
                headers=rl_res.headers,
            )

        try:
            # 3. Offload compute to thread with request timeout
            response_data = await asyncio.wait_for(
                asyncio.to_thread(service.retrieve, body.query, body.top_k),
                timeout=cfg.request_timeout_seconds,
            )
            headers = rl_res.headers
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_data.model_dump(),
                headers=headers,
            )

        except asyncio.TimeoutError:
            logger.error("Request timed out during retrieval", extra={"client_ip": client_ip})
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "Retrieval processing timed out."},
                headers=rl_res.headers,
            )
        except HostedRetrievalUnavailableError as exc:
            logger.error(
                "Vector store unavailable",
                extra={"error": str(exc), "client_ip": client_ip},
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Knowledge base vector store is currently unavailable."},
                headers=rl_res.headers,
            )
        except HostedRetrievalError as exc:
            logger.error("Retrieval error", extra={"error": str(exc), "client_ip": client_ip})
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "An error occurred during chunk retrieval."},
                headers=rl_res.headers,
            )
        finally:
            concurrency_semaphore.release()

    return app


app = create_app()


def start() -> None:
    """CLI runner for the hosted retrieval server."""
    settings = get_service_settings()
    uvicorn.run(
        "retrieval_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    start()

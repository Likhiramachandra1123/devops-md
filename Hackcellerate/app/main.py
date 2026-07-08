"""FastAPI application entry."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app import __version__
from app.api.chat import router as chat_router
from app.api.ingest import router as ingest_router
from app.api.models import router as models_router
from app.api.sessions import router as sessions_router
from app.api.sources import router as sources_router
from app.config import get_settings
from app.core.embeddings import get_embedding_model
from app.core.vector_store import get_vector_store
from app.db.session_store import get_session_store
from app.models import HealthResponse


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(sys.stdout, level=level, backtrace=False, diagnose=False,
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{line} | {message}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    _configure_logging(s.log_level)
    logger.info(f"Starting RegView v{__version__} (env={s.app_env})")
    # Warm up singletons
    await get_session_store().init()
    get_vector_store()
    get_embedding_model()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down RegView.")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="RegView — AI Regulatory Search",
        version=__version__,
        description=(
            "Conversational RAG over openFDA, FAERS, ClinicalTrials.gov, and Orange Book. "
            "Powered by PubMedBERT embeddings + ChromaDB + Anthropic Claude."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router)
    app.include_router(sessions_router)
    app.include_router(ingest_router)
    app.include_router(sources_router)
    app.include_router(models_router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health():
        return HealthResponse(
            status="ok",
            version=__version__,
            model=s.claude_model,
            embedding_model=s.embedding_model,
            vector_store_count=get_vector_store().count(),
        )

    @app.get("/", tags=["health"])
    async def root():
        return {"name": "RegView", "version": __version__, "docs": "/docs"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=(settings.app_env == "dev"))

"""Intra AI API -- FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from app.routes.applications import router as applications_router
from app.routes.auth import router as auth_router
from app.routes.candidates import router as candidates_router
from app.routes.evaluation import router as evaluation_router
from app.routes.health import router as health_router
from app.routes.interview_templates import router as interview_templates_router
from app.routes.interviews import router as interviews_router
from app.routes.jobs import router as jobs_router
from app.routes.reports import reports_router as reports_index_router
from app.routes.reports import router as reports_router
from app.routes.scheduling import router as scheduling_router
from app.routes.sessions import router as sessions_router
from app.custom_llm import custom_llm_router
from app.voice.routes import router as voice_assistants_router

# ── Structured logging ───────────────────────────────────


def _configure_logging() -> None:
    """Set up structlog with JSON rendering for production."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.APP_ENV == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO if not settings.DEBUG else logging.DEBUG)


# ── Lifespan ─────────────────────────────────────────────

logger = structlog.stdlib.get_logger("intra_ai")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared resources on startup, tear down on shutdown."""
    _configure_logging()
    logger.info("starting", env=settings.APP_ENV)

    # Supabase client (sync SDK -- lightweight, no teardown needed)
    try:
        from supabase import create_client

        _app.state.supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info("supabase_connected")
    except Exception as e:
        logger.warning("supabase_init_failed", error_type=type(e).__name__)
        _app.state.supabase = None

    # Redis
    try:
        _app.state.redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        try:
            await _app.state.redis.ping()
            logger.info("redis_connected")
        except Exception:
            logger.warning("redis_unavailable")
    except Exception as e:
        logger.warning("redis_init_failed", error_type=type(e).__name__)
        _app.state.redis = None

    # Reuse Groq TLS/HTTP connections for M1 and the orchestrator on this loop.
    from app.integrations.groq_client import initialize_groq_client, close_groq_client
    await initialize_groq_client()
    from app.integrations.aicredits_transport import initialize_aicredits_client, close_aicredits_client
    await initialize_aicredits_client()

    # Optional auxiliary project: failure here must not change official
    # Alex/Jordan availability. Sessions and confirmation state use Redis.
    _app.state.voice_assistants = None
    if settings.AGORA_TRAINING_HR_APP_ID:
        try:
            from app.voice.service import VoiceAssistantService
            await _app.state.redis.ping()
            service = VoiceAssistantService(_app.state.supabase, _app.state.redis)
            service.start_reaper()
            _app.state.voice_assistants = service
            logger.info("auxiliary_voice_ready", project="training_hr")
        except Exception as exc:
            logger.warning("auxiliary_voice_unavailable", error_type=type(exc).__name__)

    try:
        yield
    finally:
        # Complete response/persistence work before closing its HTTP pool.
        from app.custom_llm.adapter import custom_llm_adapter
        try:
            if _app.state.voice_assistants:
                await _app.state.voice_assistants.shutdown()
            await custom_llm_adapter.drain_background_tasks()
        finally:
            await close_groq_client()
            await close_aicredits_client()
            if getattr(_app.state, "redis", None):
                try:
                    await _app.state.redis.aclose()
                except Exception:
                    pass
            logger.info("shutdown_complete")


# ── App factory ──────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="Intra AI API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # ── CORS ─────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.FRONTEND_URL,
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware (order matters: outermost first) ─
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # ── Exception handlers ───────────────────────────
    register_exception_handlers(app)

    # ── Routers ──────────────────────────────────────────
    api = "/api/v1"
    if settings.CANDIDATE_ONBOARDING_ENABLED:
        from app.candidate_onboarding.routes import router as onboarding_router
        app.include_router(onboarding_router, prefix=api)
    if settings.COMPANY_KNOWLEDGE_ENABLED:
        from app.company_knowledge.routes import router as company_knowledge_router
        app.include_router(company_knowledge_router, prefix=api)
    if settings.ROLE_PLAY_ENABLED:
        from app.role_play.routes import router as role_play_router
        app.include_router(role_play_router, prefix=api)
    if settings.GROUP_DISCUSSION_ENABLED:
        from app.group_discussion.routes import router as group_discussion_router
        app.include_router(group_discussion_router, prefix=api)
    app.include_router(health_router, prefix=api)
    app.include_router(interview_templates_router, prefix=api)
    app.include_router(auth_router, prefix=api)
    app.include_router(jobs_router, prefix=api)
    app.include_router(applications_router, prefix=api)
    app.include_router(scheduling_router, prefix=api)
    app.include_router(interviews_router, prefix=api)
    app.include_router(evaluation_router, prefix=api)
    app.include_router(reports_router, prefix=api)
    app.include_router(reports_index_router, prefix=api)
    app.include_router(candidates_router, prefix=api)
    # ── Interview Session (candidate-facing meeting + platform contract) ──
    app.include_router(sessions_router, prefix=api)
    app.include_router(voice_assistants_router, prefix=api)

    # ── Custom LLM Adapter for Agora Conversational AI ─
    # Mounted at /v1 for standard OpenAI base_url and /api/v1 for repository convention
    app.include_router(custom_llm_router, prefix="/v1")
    app.include_router(custom_llm_router, prefix=api)

    # Root health probe (for load balancers that hit /)
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"status": "ok", "service": "intra-ai-api"}

    if settings.COMPANY_KNOWLEDGE_ENABLED:
        from app.company_knowledge.intelligence_routes import router as policy_intelligence_router
        app.include_router(policy_intelligence_router, prefix="/api/v1")

    # HTTP credential enforcement is outside the frozen Standard Interview stack.
    from app.core.custom_llm_boundary import CustomLLMCredentialBoundary
    app.add_middleware(CustomLLMCredentialBoundary, key=settings.CUSTOM_LLM_API_KEY)

    from app.integrations.standard_http_boundary import install_standard_http_boundaries
    install_standard_http_boundaries(app)

    return app


app = create_app()

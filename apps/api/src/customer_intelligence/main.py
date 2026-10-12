import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from customer_intelligence.api.routes.assistant import router as assistant_router
from customer_intelligence.api.routes.catalog import router as catalog_router
from customer_intelligence.api.routes.datasets import router as datasets_router
from customer_intelligence.api.routes.health import router as health_router
from customer_intelligence.api.routes.splits import router as splits_router
from customer_intelligence.api.routes.targets import router as targets_router
from customer_intelligence.api.routes.tasks import router as tasks_router
from customer_intelligence.api.routes.workflow import router as workflow_router
from customer_intelligence.core.body_limit import BodyLimitMiddleware
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import create_database_engine, init_database
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.services.runs import RunNotFoundError, RunReadError


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    if configuration.environment == "production" and not configuration.api_token:
        raise RuntimeError(
            "Production mode requires CI_API_TOKEN; this release is one private workspace."
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        init_database(configuration, application.state.engine)
        yield
        application.state.engine.dispose()

    application = FastAPI(title=configuration.app_name, version="0.2.0", lifespan=lifespan)
    application.state.settings = configuration
    application.state.engine = create_database_engine(configuration)
    application.dependency_overrides[get_settings] = lambda: configuration
    application.add_middleware(BodyLimitMiddleware)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=configuration.allowed_hosts)

    @application.middleware("http")
    async def controls(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        origin = request.headers.get("origin")
        if origin and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
                return JSONResponse(
                    {"code": "origin_not_allowed", "message": "Browser origin is not allowed."},
                    status_code=403,
                )
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > 11 * 1024 * 1024:
                    return JSONResponse(
                        {"code": "request_too_large", "message": "Request exceeds 11 MiB."},
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse(
                    {"code": "invalid_content_length", "message": "Invalid content length."},
                    status_code=400,
                )
        if (
            configuration.api_token
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/health"
        ):
            expected = "Bearer " + configuration.api_token.get_secret_value()
            if not secrets.compare_digest(request.headers.get("authorization", ""), expected):
                return JSONResponse(
                    {"code": "unauthorized", "message": "A valid API token is required."},
                    status_code=401,
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error(request: Request, code: str, message: object, status_code: int) -> JSONResponse:
        return JSONResponse(
            {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=status_code,
        )

    @application.exception_handler(WorkflowError)
    async def workflow_error(request: Request, exc: WorkflowError) -> JSONResponse:
        return error(request, exc.code, str(exc), exc.status_code)

    @application.exception_handler(RunNotFoundError)
    async def run_missing(request: Request, exc: RunNotFoundError) -> JSONResponse:
        return error(request, "run_not_found", str(exc), 404)

    @application.exception_handler(RunReadError)
    async def run_invalid(request: Request, exc: RunReadError) -> JSONResponse:
        return error(request, "invalid_run", str(exc), 409)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, "http_error", exc.detail, exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not reflect uploaded data or request values into validation errors.
        return error(
            request,
            "validation_error",
            [{"location": list(item["loc"]), "message": item["msg"]} for item in exc.errors()],
            422,
        )

    for router in (
        health_router,
        datasets_router,
        targets_router,
        tasks_router,
        splits_router,
        workflow_router,
        catalog_router,
        assistant_router,
    ):
        application.include_router(router, prefix="/api/v1")

    @application.get("/api/v1/capabilities")
    def capabilities() -> dict:
        return {
            "workspace_mode": "private_single_user",
            "upload_formats": ["csv", "xlsx"],
            "task_type": "binary_classification",
            "worker_required": True,
            "provider_notice": (
                "Assistant requests transmit aggregate profiles, saved task settings, "
                "metrics, and chat text to the configured Nebius endpoint. Raw "
                "customer sheets are not sent."
            ),
            "limits": {
                "upload_mib": 10,
                "rows": 50000,
                "columns": 250,
                "queued_jobs": 20,
                "extra_search_trials": 8,
                "job_seconds": configuration.worker_timeout_seconds,
            },
        }

    return application


app = create_app()

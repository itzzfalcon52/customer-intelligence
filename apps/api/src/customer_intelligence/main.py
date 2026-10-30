import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from customer_intelligence.api.routes.assistant import router as assistant_router
from customer_intelligence.api.routes.briefs import router as briefs_router
from customer_intelligence.api.routes.catalog import router as catalog_router
from customer_intelligence.api.routes.connections import router as connections_router
from customer_intelligence.api.routes.datasets import router as datasets_router
from customer_intelligence.api.routes.email import router as email_router
from customer_intelligence.api.routes.governance import router as governance_router
from customer_intelligence.api.routes.health import router as health_router
from customer_intelligence.api.routes.investigations import router as investigations_router
from customer_intelligence.api.routes.operations import router as operations_router
from customer_intelligence.api.routes.playbooks import router as playbooks_router
from customer_intelligence.api.routes.retention import router as retention_router
from customer_intelligence.api.routes.sources import router as sources_router
from customer_intelligence.api.routes.splits import router as splits_router
from customer_intelligence.api.routes.targets import router as targets_router
from customer_intelligence.api.routes.tasks import router as tasks_router
from customer_intelligence.api.routes.workflow import router as workflow_router
from customer_intelligence.api.routes.workspace import router as workspace_router
from customer_intelligence.core.body_limit import BodyLimitMiddleware
from customer_intelligence.core.config import Settings, get_settings
from customer_intelligence.core.database import create_database_engine, init_database
from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.core.identity import (
    Identity,
    request_settings,
    scoped_settings,
    verify_identity,
)
from customer_intelligence.core.permissions import denied
from customer_intelligence.services.audit import record_request
from customer_intelligence.services.runs import RunNotFoundError, RunReadError


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    if (
        configuration.environment == "production"
        and configuration.auth_mode == "private"
        and not configuration.api_token
    ):
        raise RuntimeError(
            "Production mode requires CI_API_TOKEN; this release is one private workspace."
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if configuration.auth_mode == "private":
            init_database(configuration, application.state.engine)
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            application.state.auth_client = client
            yield
        application.state.engine.dispose()

    application = FastAPI(title=configuration.app_name, version="0.2.0", lifespan=lifespan)
    application.state.settings = configuration
    application.state.engine = create_database_engine(configuration)
    application.dependency_overrides[get_settings] = request_settings
    upload_bytes = configuration.max_upload_mb * 1024 * 1024
    upload_paths = {
        "/api/v1/datasets/upload": upload_bytes + 1024 * 1024,
        # A source bundle carries up to four tables.
        "/api/v1/sources/upload": 4 * upload_bytes + 1024 * 1024,
        "/api/v1/playbooks": 2 * 1024 * 1024,
    }

    def body_limit(path: str) -> int:
        if path in upload_paths:
            return upload_paths[path]
        return 2 * 1024 * 1024

    application.add_middleware(BodyLimitMiddleware, limit_for=body_limit)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=configuration.allowed_hosts)

    @application.middleware("http")
    async def controls(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        origin = request.headers.get("origin")
        if origin and request.method not in {"GET", "HEAD", "OPTIONS"}:
            allowed = (
                origin == configuration.auth_public_origin
                if configuration.auth_mode == "account"
                else urlparse(origin).hostname in {"localhost", "127.0.0.1", "::1"}
            )
            if not allowed:
                return JSONResponse(
                    {"code": "origin_not_allowed", "message": "Browser origin is not allowed."},
                    status_code=403,
                )
        protected = request.url.path.startswith("/api/") and request.url.path != "/api/v1/health"
        if protected and configuration.auth_mode == "account":
            try:
                identity = await verify_identity(request, configuration)
                request.state.identity = identity
                request.state.workspace_settings = scoped_settings(configuration, identity)
            except HTTPException as exc:
                return JSONResponse(
                    {
                        "code": "unauthorized" if exc.status_code == 401 else "auth_unavailable",
                        "message": exc.detail,
                    },
                    status_code=exc.status_code,
                    headers={"Cache-Control": "no-store"},
                )
        if configuration.auth_mode == "private" and (
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
        identity = getattr(request.state, "identity", None) or Identity("local")
        request.state.identity = identity
        if protected:
            reason = denied(identity.role, request.method, request.url.path)
            if reason:
                return JSONResponse(
                    {"code": "forbidden", "message": reason},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if (
            protected
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and response.status_code < 400
        ):
            record_request(request_settings(request), identity, request, response.status_code)
        response.headers["X-Request-ID"] = request.state.request_id
        if protected:
            response.headers["Cache-Control"] = "no-store"
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
        retention_router,
        catalog_router,
        assistant_router,
        investigations_router,
        workspace_router,
        sources_router,
        connections_router,
        playbooks_router,
        operations_router,
        governance_router,
        briefs_router,
        email_router,
    ):
        application.include_router(router, prefix="/api/v1")

    @application.get("/api/v1/worker")
    def worker_status() -> dict:
        import fcntl

        path = configuration.data_directory / "worker.lock"
        if not path.exists():
            return {"running": False}
        with path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"running": True}
            fcntl.flock(lock, fcntl.LOCK_UN)
        return {"running": False}

    @application.get("/api/v1/capabilities")
    def capabilities() -> dict:
        return {
            "workspace_mode": "isolated_account"
            if configuration.auth_mode == "account"
            else "private_single_user",
            "upload_formats": ["csv", "xlsx"],
            "task_type": "binary_classification",
            "worker_required": True,
            "provider_notice": (
                "Assistant requests transmit aggregate profiles, saved task settings, "
                "metrics, and chat text to the configured Nebius endpoint. Raw "
                "customer sheets are not sent. Outreach drafting can additionally send "
                "explicitly selected feature values for up to five customers; IDs stay local."
            ),
            "limits": {
                "upload_mib": configuration.max_upload_mb,
                "excel_mib": configuration.max_excel_mb,
                "rows": configuration.max_rows,
                "columns": configuration.max_columns,
                "queued_jobs": 20,
                "extra_search_trials": 8,
                "job_seconds": configuration.worker_timeout_seconds,
            },
        }

    return application


app = create_app()

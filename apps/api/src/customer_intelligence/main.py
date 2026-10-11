from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from customer_intelligence.api.routes.datasets import router as datasets_router
from customer_intelligence.api.routes.health import router as health_router
from customer_intelligence.api.routes.targets import router as targets_router
from customer_intelligence.api.routes.tasks import router as tasks_router
from customer_intelligence.api.routes.splits import router as splits_router
from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import init_database




settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(datasets_router, prefix="/api/v1")
app.include_router(targets_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(splits_router, prefix="/api/v1")
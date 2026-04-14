from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from src.api.middleware import RequestLoggingMiddleware
from src.api.routers import auth, balance, generations, health, webhooks
from src.core.config import settings
from src.core.logging import setup_logging
from src.infrastructure.database.models import Base
from src.infrastructure.database.repositories.price_repo import SQLAlchemyPriceRepository
from src.infrastructure.database.session import get_engine, get_session_factory

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_session_factory()
    async with factory() as session:
        price_repo = SQLAlchemyPriceRepository(session)
        await price_repo.ensure_defaults()
        await session.commit()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(RequestLoggingMiddleware)

    from src.admin import setup_admin

    setup_admin(application, get_engine())

    metrics_app = make_asgi_app()
    application.mount("/metrics", metrics_app)

    application.include_router(health.router)
    application.include_router(auth.router, prefix="/auth", tags=["auth"])
    application.include_router(balance.router, prefix="/balance", tags=["balance"])
    application.include_router(generations.router, prefix="/generations", tags=["generations"])
    application.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    async def root():
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()

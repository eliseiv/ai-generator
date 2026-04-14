# pylint: disable=wrong-import-position,redefined-outer-name
import os

os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5432"
os.environ["DB_NAME"] = "test"
os.environ["DB_USER"] = "test"
os.environ["DB_PASSWORD"] = "test"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_PASS"] = ""
os.environ["FAL_KEY"] = "test-key"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_fake"
os.environ["PAYMENT_WEBHOOK_SECRET"] = "test-webhook-secret-key"
os.environ["FAL_KEY_FALLBACK"] = "test-fallback-key"

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.database.models import Base, GenerationPrice, GenerationType

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(test_engine):
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(GenerationPrice))
        if not result.scalars().first():
            defaults = {
                GenerationType.TEXT_TO_IMAGE: Decimal("10.00"),
                GenerationType.IMAGE_TO_IMAGE: Decimal("10.00"),
                GenerationType.TEXT_TO_VIDEO: Decimal("50.00"),
                GenerationType.IMAGE_TO_VIDEO: Decimal("50.00"),
            }
            for gen_type, cost in defaults.items():
                session.add(GenerationPrice(generation_type=gen_type, cost=cost))
            await session.commit()
    return factory


@pytest_asyncio.fixture
async def test_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        yield

    with patch("src.api.middleware.check_rate_limit", new_callable=AsyncMock) as mock_rl:
        mock_rl.return_value = (True, 9)

        from src.api.middleware import RequestLoggingMiddleware
        from src.api.routers import auth, balance, generations, health, webhooks
        from src.infrastructure.database.session import get_session

        test_app = FastAPI(lifespan=test_lifespan)
        test_app.add_middleware(RequestLoggingMiddleware)

        test_app.include_router(health.router)
        test_app.include_router(auth.router, prefix="/auth", tags=["auth"])
        test_app.include_router(balance.router, prefix="/balance", tags=["balance"])
        test_app.include_router(generations.router, prefix="/generations", tags=["generations"])
        test_app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])

        test_app.dependency_overrides[get_session] = override_get_session

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def signed_payment_headers(payload: dict) -> dict[str, str]:
    """Build headers with valid HMAC signature for payment webhook calls."""
    from src.core.security import compute_webhook_signature

    body = json.dumps(payload).encode()
    sig = compute_webhook_signature(body, "test-webhook-secret-key")
    return {
        "content-type": "application/json",
        "x-webhook-signature": sig,
    }


async def topup_user(client: AsyncClient, external_user_id: str, amount: int) -> None:
    """Helper: top-up balance via signed payment webhook."""
    payload = {"external_user_id": external_user_id, "amount": amount}
    body = json.dumps(payload).encode()
    headers = signed_payment_headers(payload)
    await client.post("/webhooks/payment", content=body, headers=headers)

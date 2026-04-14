import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={"external_user_id": "unique-user-123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "api_key" in data
    assert len(data["api_key"]) > 20


@pytest.mark.asyncio
async def test_register_duplicate_user(client: AsyncClient):
    ext_id = "duplicate-user-456"
    await client.post("/auth/register", json={"external_user_id": ext_id})
    response = await client.post("/auth/register", json={"external_user_id": ext_id})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_empty_external_id(client: AsyncClient):
    response = await client.post("/auth/register", json={"external_user_id": ""})
    assert response.status_code == 422

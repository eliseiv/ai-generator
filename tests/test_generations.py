from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.conftest import topup_user


async def _create_funded_user(client: AsyncClient, ext_id: str) -> str:
    reg = await client.post("/auth/register", json={"external_user_id": ext_id})
    api_key = reg.json()["api_key"]
    await topup_user(client, ext_id, 500)
    return api_key


@pytest.mark.asyncio
async def test_create_text_to_image_insufficient_balance(client: AsyncClient):
    reg = await client.post("/auth/register", json={"external_user_id": "gen-user-poor"})
    api_key = reg.json()["api_key"]

    response = await client.post(
        "/generations/text-to-image",
        json={"prompt": "A sunset over mountains"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 402


@pytest.mark.asyncio
async def test_create_text_to_image_success(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-t2i")

    with patch("src.api.routers.generations._dispatch_generation"):
        response = await client.post(
            "/generations/text-to-image",
            json={"prompt": "A beautiful landscape"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "created"
        assert data["type"] == "text_to_image"
        assert float(data["cost"]) == 10.0


@pytest.mark.asyncio
async def test_create_text_to_video_success(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-t2v")

    with patch("src.api.routers.generations._dispatch_generation"):
        response = await client.post(
            "/generations/text-to-video",
            json={"prompt": "A dragon flying over a castle"},
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["type"] == "text_to_video"
        assert float(data["cost"]) == 50.0


@pytest.mark.asyncio
async def test_create_image_to_image_success(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-i2i")

    with patch("src.api.routers.generations._dispatch_generation"):
        response = await client.post(
            "/generations/image-to-image",
            json={
                "prompt": "Make it look like a painting",
                "image_urls": ["https://example.com/image.png"],
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["type"] == "image_to_image"


@pytest.mark.asyncio
async def test_create_image_to_video_success(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-i2v")

    with patch("src.api.routers.generations._dispatch_generation"):
        response = await client.post(
            "/generations/image-to-video",
            json={
                "prompt": "Animate the warrior",
                "image_url": "https://example.com/warrior.jpg",
            },
            headers={"X-API-Key": api_key},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["type"] == "image_to_video"


@pytest.mark.asyncio
async def test_list_generations(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-list")

    with patch("src.api.routers.generations._dispatch_generation"):
        await client.post(
            "/generations/text-to-image",
            json={"prompt": "Test prompt"},
            headers={"X-API-Key": api_key},
        )

    response = await client.get("/generations", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_get_generation_status(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-status")

    with patch("src.api.routers.generations._dispatch_generation"):
        create_resp = await client.post(
            "/generations/text-to-image",
            json={"prompt": "Status check prompt"},
            headers={"X-API-Key": api_key},
        )
        task_id = create_resp.json()["task_id"]

    response = await client.get(f"/generations/{task_id}", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == task_id
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_get_generation_not_found(client: AsyncClient):
    api_key = await _create_funded_user(client, "gen-user-404")

    response = await client.get(
        "/generations/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generation_no_auth(client: AsyncClient):
    response = await client.post(
        "/generations/text-to-image",
        json={"prompt": "No auth test"},
    )
    assert response.status_code == 401

import json

import pytest
from httpx import AsyncClient

from tests.conftest import signed_payment_headers, topup_user


@pytest.mark.asyncio
async def test_get_balance_unauthorized(client: AsyncClient):
    response = await client.get("/balance")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_balance(client: AsyncClient):
    reg = await client.post("/auth/register", json={"external_user_id": "balance-user-001"})
    api_key = reg.json()["api_key"]

    response = await client.get("/balance", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == "0.00"


@pytest.mark.asyncio
async def test_payment_webhook(client: AsyncClient):
    ext_id = "balance-user-002"
    reg = await client.post("/auth/register", json={"external_user_id": ext_id})
    api_key = reg.json()["api_key"]

    payload = {"external_user_id": ext_id, "amount": 100}
    response = await client.post(
        "/webhooks/payment",
        content=json.dumps(payload).encode(),
        headers=signed_payment_headers(payload),
    )
    assert response.status_code == 200
    data = response.json()
    assert float(data["new_balance"]) == 100.0

    bal = await client.get("/balance", headers={"X-API-Key": api_key})
    assert float(bal.json()["balance"]) == 100.0


@pytest.mark.asyncio
async def test_payment_webhook_unknown_user(client: AsyncClient):
    payload = {"external_user_id": "nonexistent-user", "amount": 50}
    response = await client.post(
        "/webhooks/payment",
        content=json.dumps(payload).encode(),
        headers=signed_payment_headers(payload),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_payment_webhook_no_signature(client: AsyncClient):
    response = await client.post(
        "/webhooks/payment",
        json={"external_user_id": "some-user", "amount": 50},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_payment_webhook_bad_signature(client: AsyncClient):
    response = await client.post(
        "/webhooks/payment",
        content=b'{"external_user_id": "x", "amount": 50}',
        headers={
            "content-type": "application/json",
            "x-webhook-signature": "invalid-signature-value",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_transactions(client: AsyncClient):
    ext_id = "balance-user-003"
    reg = await client.post("/auth/register", json={"external_user_id": ext_id})
    api_key = reg.json()["api_key"]

    await topup_user(client, ext_id, 200)

    response = await client.get("/balance/transactions", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
    assert data["items"][0]["type"] == "topup"

import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.conftest import fal_webhook_token, topup_user


@pytest.mark.asyncio
async def test_fal_webhook_no_token(client: AsyncClient):
    response = await client.post(
        "/webhooks/fal/00000000-0000-0000-0000-000000000000",
        json={"images": [{"url": "https://example.com/img.png"}]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_fal_webhook_bad_token(client: AsyncClient):
    response = await client.post(
        "/webhooks/fal/00000000-0000-0000-0000-000000000000?token=invalid",
        json={"images": [{"url": "https://example.com/img.png"}]},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_fal_webhook_unknown_task(client: AsyncClient):
    task_id = "00000000-0000-0000-0000-000000000000"
    token = fal_webhook_token(task_id)
    response = await client.post(
        f"/webhooks/fal/{task_id}?token={token}",
        json={"images": [{"url": "https://example.com/img.png"}]},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_fal_webhook_completes_task(client: AsyncClient):
    ext_id = "wh-user-001"
    reg = await client.post("/auth/register", json={"external_user_id": ext_id})
    api_key = reg.json()["api_key"]

    await topup_user(client, ext_id, 500)

    with patch("src.api.routers.generations._dispatch_generation"):
        create_resp = await client.post(
            "/generations/text-to-image",
            json={"prompt": "Webhook test prompt"},
            headers={"X-API-Key": api_key},
        )
        task_id = create_resp.json()["task_id"]

    with patch("src.workers.webhook_tasks.deliver_webhook") as mock_wh:
        mock_wh.delay = lambda *a, **kw: None
        token = fal_webhook_token(task_id)

        fal_resp = await client.post(
            f"/webhooks/fal/{task_id}?token={token}",
            json={
                "images": [
                    {"url": "https://fal.media/files/test.png", "content_type": "image/png"}
                ],
                "seeds": [12345],
            },
        )
        assert fal_resp.status_code == 200

    status_resp = await client.get(f"/generations/{task_id}", headers={"X-API-Key": api_key})
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "completed"
    assert "fal.media" in data["result_url"]


@pytest.mark.asyncio
async def test_fal_webhook_error_triggers_refund(client: AsyncClient):
    ext_id = "wh-user-refund"
    reg = await client.post("/auth/register", json={"external_user_id": ext_id})
    api_key = reg.json()["api_key"]

    await topup_user(client, ext_id, 500)

    bal_before = await client.get("/balance", headers={"X-API-Key": api_key})
    balance_before = float(bal_before.json()["balance"])

    with patch("src.api.routers.generations._dispatch_generation"):
        create_resp = await client.post(
            "/generations/text-to-image",
            json={"prompt": "Refund test prompt"},
            headers={"X-API-Key": api_key},
        )
        task_id = create_resp.json()["task_id"]
        cost = float(create_resp.json()["cost"])

    token = fal_webhook_token(task_id)
    fal_resp = await client.post(
        f"/webhooks/fal/{task_id}?token={token}",
        json={"error": "Generation failed due to content filter"},
    )
    assert fal_resp.status_code == 200

    bal_after = await client.get("/balance", headers={"X-API-Key": api_key})
    balance_after = float(bal_after.json()["balance"])

    assert balance_after == pytest.approx(balance_before - cost + cost)


# --- Stripe webhook tests ---


def _make_stripe_event(event_type: str, data_object: dict) -> dict:
    return {
        "id": "evt_test_123",
        "type": event_type,
        "data": {"object": data_object},
    }


@pytest.mark.asyncio
async def test_stripe_webhook_checkout_completed(client: AsyncClient):
    ext_id = "stripe-user-001"
    await client.post("/auth/register", json={"external_user_id": ext_id})

    event = _make_stripe_event(
        "checkout.session.completed",
        {
            "amount_total": 1000,
            "currency": "usd",
            "metadata": {"external_user_id": ext_id},
        },
    )

    with patch("stripe.Webhook.construct_event", return_value=event):
        response = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={
                "stripe-signature": "fake_sig",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["external_user_id"] == ext_id
    assert float(data["tokens_added"]) == 1000.0


@pytest.mark.asyncio
async def test_stripe_webhook_payment_intent_succeeded(client: AsyncClient):
    ext_id = "stripe-user-002"
    await client.post("/auth/register", json={"external_user_id": ext_id})

    event = _make_stripe_event(
        "payment_intent.succeeded",
        {
            "amount": 500,
            "currency": "usd",
            "metadata": {"external_user_id": ext_id},
        },
    )

    with patch("stripe.Webhook.construct_event", return_value=event):
        response = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={
                "stripe-signature": "fake_sig",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert float(data["tokens_added"]) == 500.0


@pytest.mark.asyncio
async def test_stripe_webhook_no_signature(client: AsyncClient):
    """Missing Stripe-Signature header -> Stripe SDK raises SignatureVerificationError."""
    with patch(
        "stripe.Webhook.construct_event",
        side_effect=__import__("stripe").SignatureVerificationError(
            "No signatures found matching the expected signature for payload",
            "",
        ),
    ):
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"type": "test"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature(client: AsyncClient):
    """Tampered / wrong Stripe-Signature -> 400."""
    with patch(
        "stripe.Webhook.construct_event",
        side_effect=__import__("stripe").SignatureVerificationError("Invalid", "sig_header"),
    ):
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"type": "test"}',
            headers={
                "stripe-signature": "t=123,v1=bad",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_payload(client: AsyncClient):
    """Malformed body -> Stripe SDK raises ValueError -> 400."""
    with patch(
        "stripe.Webhook.construct_event",
        side_effect=ValueError("Invalid payload"),
    ):
        response = await client.post(
            "/webhooks/stripe",
            content=b"not-json-at-all",
            headers={
                "stripe-signature": "t=123,v1=abc",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 400
    assert "payload" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stripe_webhook_unhandled_event(client: AsyncClient):
    event = _make_stripe_event("customer.created", {"id": "cus_123"})

    with patch("stripe.Webhook.construct_event", return_value=event):
        response = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={
                "stripe-signature": "fake_sig",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_stripe_webhook_unknown_user(client: AsyncClient):
    event = _make_stripe_event(
        "checkout.session.completed",
        {
            "amount_total": 1000,
            "currency": "usd",
            "metadata": {"external_user_id": "nonexistent-stripe-user"},
        },
    )

    with patch("stripe.Webhook.construct_event", return_value=event):
        response = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={
                "stripe-signature": "fake_sig",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 400

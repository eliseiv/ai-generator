# pylint: disable=import-error
"""
Load tests for AI Generation Microservice.

Validates the SLA requirement: API response time <= 5 seconds.

Usage:
    # 1. Start the service with DRY_RUN=true to skip Celery dispatch:
    #    DRY_RUN=true docker compose up -d app postgres redis

    # 2. Interactive (web UI on http://localhost:8089):
    locust -f loadtests/locustfile.py --host http://localhost:8000

    # 3. Headless (CI-friendly):
    locust -f loadtests/locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 10 --run-time 60s \
        --csv loadtests/results

Environment variables (set before running locust):
    LOADTEST_API_KEY        - API key of a pre-registered, funded user (optional)
    LOADTEST_WEBHOOK_SECRET - PAYMENT_WEBHOOK_SECRET value for auto-topup

Note on POST /generations/*:
    These endpoints create real DB records and deduct tokens, but the actual
    Fal.ai submission is skipped when the server runs with DRY_RUN=true.
    This isolates the SLA measurement to our API layer (DB + validation +
    response serialization) without depending on external AI services.
"""

import hashlib
import hmac
import json
import os
import random

from locust import HttpUser, between, events, task

API_KEY = os.environ.get("LOADTEST_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("LOADTEST_WEBHOOK_SECRET", "")

PROMPTS = [
    "A serene mountain landscape at dawn with mist rolling through the valleys",
    "A cyberpunk city street at night with neon signs and rain reflections",
    "An ancient temple hidden in a tropical jungle, overgrown with vines",
    "A majestic dragon perched on a snowy cliff under the northern lights",
    "A cozy cabin in the woods during autumn with golden leaves falling",
]

IMAGE_URLS = [
    "https://storage.googleapis.com/falserverless/model_tests/wan/dragon-warrior.jpg",
]


class AIGeneratorUser(HttpUser):
    """Simulates a typical API consumer hitting all major endpoints."""

    wait_time = between(1, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ext_id: str = ""
        self.api_key: str = ""
        self.headers: dict[str, str] = {}

    def on_start(self):
        if not API_KEY:
            self.ext_id = f"loadtest-{random.randint(100000, 999999)}"
            resp = self.client.post(
                "/auth/register",
                json={"external_user_id": self.ext_id},
            )
            if resp.status_code == 201:
                self.api_key = resp.json()["api_key"]
                self._topup(100000)
            else:
                self.api_key = ""
                self.ext_id = ""
        else:
            self.api_key = API_KEY
            self.ext_id = ""

        self.headers = {"X-API-Key": self.api_key}

    @staticmethod
    def _sign(body: bytes) -> str:
        return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    def _topup(self, amount: int) -> None:
        if not WEBHOOK_SECRET or not self.ext_id:
            return
        payload = {"external_user_id": self.ext_id, "amount": amount}
        body = json.dumps(payload).encode()
        self.client.post(
            "/webhooks/payment",
            data=body,
            headers={
                "content-type": "application/json",
                "x-webhook-signature": self._sign(body),
            },
            name="/webhooks/payment [topup]",
        )

    # --- Read-heavy tasks (typical consumer) ---

    @task(5)
    def get_balance(self):
        self.client.get("/balance", headers=self.headers)

    @task(3)
    def list_generations(self):
        self.client.get("/generations?limit=10", headers=self.headers)

    @task(2)
    def get_transactions(self):
        self.client.get("/balance/transactions?limit=10", headers=self.headers)

    @task(1)
    def healthcheck(self):
        self.client.get("/health")

    # --- Write tasks (generation creation) ---
    # Requires DRY_RUN=true on the server to skip Celery dispatch.
    # Measures: input validation, auth, balance check, DB insert, response.

    @task(2)
    def create_text_to_image(self):
        self.client.post(
            "/generations/text-to-image",
            json={
                "prompt": random.choice(PROMPTS),
                "image_size": "square",
            },
            headers=self.headers,
            name="/generations/text-to-image",
        )

    @task(1)
    def create_image_to_image(self):
        self.client.post(
            "/generations/image-to-image",
            json={
                "prompt": random.choice(PROMPTS),
                "image_urls": [random.choice(IMAGE_URLS)],
                "image_size": "square",
            },
            headers=self.headers,
            name="/generations/image-to-image",
        )

    @task(1)
    def create_text_to_video(self):
        self.client.post(
            "/generations/text-to-video",
            json={
                "prompt": random.choice(PROMPTS),
                "resolution": "480p",
                "duration": "5",
            },
            headers=self.headers,
            name="/generations/text-to-video",
        )

    @task(1)
    def create_image_to_video(self):
        self.client.post(
            "/generations/image-to-video",
            json={
                "prompt": random.choice(PROMPTS),
                "image_url": random.choice(IMAGE_URLS),
                "resolution": "480p",
                "duration": "5",
            },
            headers=self.headers,
            name="/generations/image-to-video",
        )


@events.quitting.add_listener
def check_sla(environment, **kwargs):
    """Fail the load test if 95th percentile exceeds 5 seconds."""
    sla_ms = 5000
    failures = []

    for stat in environment.runner.stats.entries.values():
        p95 = stat.get_response_time_percentile(0.95) or 0
        if p95 > sla_ms:
            failures.append(f"{stat.name}: p95={p95:.0f}ms > {sla_ms}ms")

    if failures:
        environment.process_exit_code = 1
        print(f"\nSLA VIOLATIONS (p95 > {sla_ms}ms):")
        for f in failures:
            print(f"  - {f}")
    else:
        print(f"\nSLA CHECK PASSED: all endpoints p95 < {sla_ms}ms")

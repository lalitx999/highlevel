import base64
import hashlib
import hmac
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app
from app.core.config import settings


@pytest.mark.asyncio
async def test_health_check_endpoint():
    with patch("app.routers.health.check_database_health", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "UP"
            assert data["checks"]["database"] == "CONNECTED"
            assert "X-Trace-Id" in response.headers


@pytest.mark.asyncio
async def test_line_webhook_unauthorized_missing_signature():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/webhooks/line", content=b'{"events":[]}')
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_line_webhook_valid_signature_fast_return():
    secret = "unit_test_secret"
    body = b'{"events":[]}'
    hash_digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    sig = base64.b64encode(hash_digest).decode("utf-8")

    with patch.object(settings, "LINE_CHANNEL_SECRET", secret):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/webhooks/line",
                content=body,
                headers={"x-line-signature": sig, "Content-Type": "application/json"},
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ghl_outbound_echo_suppression():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Inbound direction echo
        payload = {
            "type": "InboundMessage",
            "direction": "inbound",
            "contactId": "cnt_123",
            "body": "hello from user",
        }
        response = await ac.post("/api/webhooks/highlevel/outbound", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        assert response.json()["reason"] == "inbound_echo_suppressed"

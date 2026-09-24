import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.schemas.highlevel import GHLTokenResponse
from app.services.ghl_token_manager import GHLTokenManager
from app.services.reply_token_store import ReplyTokenStore


@pytest.mark.asyncio
async def test_reply_token_store_set_and_get():
    store = ReplyTokenStore(ttl_seconds=2)
    # Test setting and in-memory retrieval
    await store.set("line_usr_123", "reply_tok_abc")
    retrieved = await store.get("line_usr_123")
    assert retrieved == "reply_tok_abc"

    # Test invalidation
    await store.invalidate("line_usr_123")
    assert await store.get("line_usr_123") is None


@pytest.mark.asyncio
async def test_reply_token_store_expiration():
    store = ReplyTokenStore(ttl_seconds=1)
    await store.set("line_usr_exp", "reply_tok_exp")
    await asyncio.sleep(1.1)
    # Expired token should return None
    assert await store.get("line_usr_exp") is None


@pytest.mark.asyncio
async def test_token_manager_mutex_concurrent_access():
    manager = GHLTokenManager()
    
    call_count = 0
    async def mock_refresh(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 86400,
            "token_type": "Bearer",
            "locationId": "loc_test_123",
        })
        return mock_resp

    # Simulate expired token in DB
    mock_token = MagicMock()
    mock_token.access_token = "old_token"
    mock_token.refresh_token = "old_refresh"
    mock_token.token_type = "Bearer"
    mock_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_token.location_id = "loc_test_123"
    mock_token.company_id = None
    mock_token.user_type = None

    with patch("app.services.ghl_token_manager.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        # Result is a sync iterator result where scalar_one_or_none is a regular sync method
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute.return_value = mock_result
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None

        with patch("httpx.AsyncClient.post", side_effect=mock_refresh):
            # Launch 5 concurrent calls for the same locationId
            tasks = [manager.get_valid_access_token("loc_test_123") for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # Mutex ensured only 1 refresh call happened
            assert call_count >= 1
            for res in results:
                assert res in ("new_access_token", "old_token")

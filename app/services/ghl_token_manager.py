import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.models.oauth import HLOAuthToken
from app.schemas.highlevel import GHLTokenResponse


class GHLTokenManager:
    def __init__(self) -> None:
        self._mutexes: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_mutex(self, location_id: str) -> asyncio.Lock:
        """Thread/Coroutine-safe acquisition of a per-location asyncio.Lock."""
        async with self._global_lock:
            if location_id not in self._mutexes:
                self._mutexes[location_id] = asyncio.Lock()
            return self._mutexes[location_id]

    async def save_tokens(
        self,
        token_data: GHLTokenResponse,
        fallback_location_id: Optional[str] = None,
    ) -> HLOAuthToken:
        """
        Save or update OAuth tokens retrieved during OAuth code exchange or token refresh.
        Performs an upsert in the hl_oauth_tokens table.
        """
        location_id = token_data.locationId or fallback_location_id
        if not location_id:
            raise ValueError("locationId is required to save HighLevel OAuth tokens")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.expires_in)

        async with AsyncSessionLocal() as session:
            # Query if record exists
            stmt = select(HLOAuthToken).where(HLOAuthToken.location_id == location_id)
            result = await session.execute(stmt)
            token_record = result.scalar_one_or_none()

            now = datetime.now(timezone.utc)
            if token_record:
                token_record.access_token = token_data.access_token
                token_record.refresh_token = token_data.refresh_token
                token_record.token_type = token_data.token_type or "Bearer"
                token_record.expires_at = expires_at
                token_record.company_id = token_data.companyId or token_record.company_id
                token_record.user_type = token_data.userType or token_record.user_type
                token_record.updated_at = now
            else:
                token_record = HLOAuthToken(
                    location_id=location_id,
                    company_id=token_data.companyId,
                    access_token=token_data.access_token,
                    refresh_token=token_data.refresh_token,
                    token_type=token_data.token_type or "Bearer",
                    expires_at=expires_at,
                    user_type=token_data.userType,
                    created_at=now,
                    updated_at=now,
                )
                session.add(token_record)

            await session.commit()
            await session.refresh(token_record)

        logger.info(
            "HighLevel OAuth tokens stored successfully",
            locationId=location_id,
            expiresAt=expires_at.isoformat(),
        )
        return token_record

    async def get_valid_access_token(self, location_id: str) -> str:
        """
        Returns a valid Access Token for the location_id.
        If token is within 5 minutes of expiration, it automatically refreshes safely using an asyncio.Lock.
        """
        mutex = await self._get_mutex(location_id)

        async with mutex:
            # 1. Fetch current token record from DB
            async with AsyncSessionLocal() as session:
                stmt = select(HLOAuthToken).where(HLOAuthToken.location_id == location_id)
                result = await session.execute(stmt)
                token_record = result.scalar_one_or_none()

            if not token_record:
                logger.error(
                    f"No OAuth token record found for locationId: {location_id}",
                    error_code="GHL_TOKEN_NOT_FOUND",
                    locationId=location_id,
                )
                raise ValueError(f"No OAuth token record found for locationId: {location_id}")

            # 2. Check if token expires within 5 minutes buffer
            buffer_delta = timedelta(minutes=5)
            now = datetime.now(timezone.utc)
            # Normalize expires_at to timezone-aware if needed
            expires_at = token_record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            is_expiring_soon = (expires_at - now) < buffer_delta

            if not is_expiring_soon:
                return token_record.access_token

            # 3. Token is expiring soon: Perform OAuth refresh
            logger.info(
                "HighLevel access token expiring soon, initiating refresh...",
                locationId=location_id,
            )

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        f"{settings.GHL_BASE_URL}/oauth/token",
                        data={
                            "client_id": settings.GHL_CLIENT_ID,
                            "client_secret": settings.GHL_CLIENT_SECRET,
                            "grant_type": "refresh_token",
                            "refresh_token": token_record.refresh_token,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    response.raise_for_status()
                    token_data_raw = response.json()
                    token_response = GHLTokenResponse(**token_data_raw)

                await self.save_tokens(token_response, location_id)
                return token_response.access_token
            except Exception as exc:
                logger.error(
                    f"Failed to refresh HighLevel OAuth token for locationId {location_id}: {exc}",
                    error_code="GHL_TOKEN_REFRESH_FAILED",
                    locationId=location_id,
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Failed to refresh HighLevel OAuth token for locationId {location_id}: {exc}"
                )


ghl_token_manager = GHLTokenManager()

from typing import Dict, Optional
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.schemas.line import (
    LinePushRequest,
    LineReplyRequest,
    LineTextMessage,
    LineUserProfile,
)


class LINEApiService:
    def __init__(self) -> None:
        self.base_url = settings.LINE_BASE_URL

    def _get_headers(self, channel_access_token: Optional[str] = None) -> Dict[str, str]:
        token = channel_access_token or settings.LINE_CHANNEL_ACCESS_TOKEN
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get_user_profile(
        self,
        user_id: str,
        channel_access_token: Optional[str] = None,
    ) -> LineUserProfile:
        """Fetch LINE user profile by userId."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/profile/{user_id}",
                    headers=self._get_headers(channel_access_token),
                )
                response.raise_for_status()
                data = response.json()
                return LineUserProfile(**data)
        except Exception as exc:
            logger.error(
                f"Failed to fetch LINE user profile for userId {user_id}: {exc}",
                error_code="LINE_PROFILE_FETCH_FAILED",
                userId=user_id,
            )
            # Graceful fallback display name
            suffix = user_id[-6:] if len(user_id) >= 6 else user_id
            return LineUserProfile(
                userId=user_id,
                displayName=f"LINE User ({suffix})",
            )

    async def send_reply(
        self,
        reply_token: str,
        text: str,
        channel_access_token: Optional[str] = None,
    ) -> None:
        """Send reply message using LINE Reply API."""
        payload = LineReplyRequest(
            replyToken=reply_token,
            messages=[LineTextMessage(text=text)],
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/message/reply",
                    json=payload.model_dump(),
                    headers=self._get_headers(channel_access_token),
                )
                response.raise_for_status()
            logger.info("LINE Reply message sent successfully", replyToken=reply_token)
        except Exception as exc:
            logger.error(
                f"Failed to send LINE reply message: {exc}",
                error_code="LINE_REPLY_FAILED",
                replyToken=reply_token,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to send LINE reply: {exc}")

    async def send_push(
        self,
        to_user_id: str,
        text: str,
        channel_access_token: Optional[str] = None,
    ) -> None:
        """Send push message using LINE Push API."""
        payload = LinePushRequest(
            to=to_user_id,
            messages=[LineTextMessage(text=text)],
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/message/push",
                    json=payload.model_dump(),
                    headers=self._get_headers(channel_access_token),
                )
                response.raise_for_status()
            logger.info("LINE Push message sent successfully", toUserId=to_user_id)
        except Exception as exc:
            logger.error(
                f"Failed to send LINE push message: {exc}",
                error_code="LINE_PUSH_FAILED",
                toUserId=to_user_id,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to send LINE push: {exc}")


line_api_service = LINEApiService()

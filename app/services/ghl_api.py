from typing import Any, Dict, Optional
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.schemas.highlevel import (
    GHLContact,
    GHLContactsSearchResponse,
    GHLCreateContactPayload,
    GHLInboundMessagePayload,
)
from app.services.ghl_token_manager import ghl_token_manager


class GHLApiService:
    def __init__(self) -> None:
        self.base_url = settings.GHL_BASE_URL

    async def _get_headers(self, location_id: str) -> Dict[str, str]:
        access_token = await ghl_token_manager.get_valid_access_token(location_id)
        return {
            "Authorization": f"Bearer {access_token}",
            "Version": "2021-07-28",
            "Content-Type": "application/json",
        }

    async def find_contact_by_line_user_id(
        self,
        location_id: str,
        line_user_id: str,
    ) -> Optional[GHLContact]:
        """
        Search for a contact by line_user_id custom field or query in GHL Location.
        """
        try:
            headers = await self._get_headers(location_id)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/contacts/",
                    headers=headers,
                    params={
                        "locationId": location_id,
                        "query": line_user_id,
                        "limit": 20,
                    },
                )
                response.raise_for_status()
                data = response.json()
                search_res = GHLContactsSearchResponse(**data)

            # Match contact where line_user_id custom field or query matches
            for contact in search_res.contacts:
                if contact.customFields:
                    for field in contact.customFields:
                        key = field.get("key") or field.get("id")
                        val = field.get("value")
                        if key == "line_user_id" and val == line_user_id:
                            return contact

            return None
        except Exception as exc:
            logger.warn(
                f"Failed to query GHL contact by line_user_id: {exc}",
                locationId=location_id,
                lineUserId=line_user_id,
            )
            return None

    async def create_contact(
        self,
        payload: GHLCreateContactPayload,
    ) -> GHLContact:
        """Create a new Contact in HighLevel."""
        try:
            headers = await self._get_headers(payload.locationId)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/contacts/",
                    headers=headers,
                    json=payload.model_dump(exclude_none=True),
                )
                response.raise_for_status()
                data = response.json()
                contact_dict = data.get("contact", data)
                return GHLContact(**contact_dict)
        except Exception as exc:
            logger.error(
                f"Failed to create HighLevel contact: {exc}",
                error_code="GHL_CREATE_CONTACT_FAILED",
                locationId=payload.locationId,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to create GHL contact: {exc}")

    async def inject_inbound_message(
        self,
        location_id: str,
        payload: GHLInboundMessagePayload,
    ) -> Any:
        """Inject an Inbound message into HighLevel Conversation API v2."""
        try:
            headers = await self._get_headers(location_id)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/conversations/messages/inbound",
                    headers=headers,
                    json=payload.model_dump(exclude_none=True),
                )
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.error(
                f"Failed to inject inbound message to HighLevel: {exc}",
                error_code="GHL_INBOUND_MSG_FAILED",
                locationId=location_id,
                contactId=payload.contactId,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to inject inbound message into HighLevel: {exc}")


ghl_api_service = GHLApiService()

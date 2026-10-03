from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class GHLTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: Optional[str] = None
    userType: Optional[str] = None
    companyId: Optional[str] = None
    locationId: Optional[str] = None


class GHLCustomField(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    value: Any = None


class GHLCreateContactPayload(BaseModel):
    locationId: str
    firstName: str
    customFields: Optional[List[Dict[str, Any]]] = None


class GHLContact(BaseModel):
    id: str
    locationId: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    customFields: Optional[List[Dict[str, Any]]] = None


class GHLContactsSearchResponse(BaseModel):
    contacts: List[GHLContact] = Field(default_factory=list)


class GHLInboundMessagePayload(BaseModel):
    type: str = "SMS"
    contactId: str
    message: str
    conversationId: Optional[str] = None
    conversationProviderId: Optional[str] = None


class GHLLocationObj(BaseModel):
    id: Optional[str] = None


class GHLMessageObj(BaseModel):
    body: Optional[str] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    type: Optional[str] = None


class GHLOutboundWebhookPayload(BaseModel):
    type: Optional[str] = None
    messageType: Optional[str] = None
    locationId: Optional[str] = None
    location_id: Optional[str] = None
    location: Optional[GHLLocationObj] = None
    contactId: Optional[str] = None
    contact_id: Optional[str] = None
    id: Optional[str] = None
    body: Optional[str] = None
    message: Optional[Union[str, GHLMessageObj, Dict[str, Any]]] = None
    messageBody: Optional[str] = None
    text: Optional[str] = None
    content: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None

    def get_contact_id(self) -> Optional[str]:
        return self.contactId or self.contact_id or self.id

    def get_location_id(self) -> Optional[str]:
        if self.locationId:
            return self.locationId
        if self.location_id:
            return self.location_id
        if self.location and self.location.id:
            return self.location.id
        return None

    def get_message_text(self) -> str:
        if isinstance(self.body, str) and self.body:
            return self.body
        if isinstance(self.message, str) and self.message:
            return self.message
        if isinstance(self.message, GHLMessageObj):
            return self.message.body or self.message.text or ""
        if isinstance(self.message, dict):
            return self.message.get("body") or self.message.get("text") or ""
        if self.messageBody:
            return self.messageBody
        if self.text:
            return self.text
        if self.content:
            return self.content
        return ""

    def get_direction_string(self) -> str:
        if self.direction:
            return self.direction
        if self.messageType:
            return self.messageType
        if isinstance(self.message, GHLMessageObj) and self.message.direction:
            return self.message.direction
        if isinstance(self.message, dict):
            return self.message.get("direction") or self.message.get("type") or ""
        return ""

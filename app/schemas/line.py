from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LineWebhookSource(BaseModel):
    type: str = "user"
    userId: Optional[str] = None
    groupId: Optional[str] = None
    roomId: Optional[str] = None


class LineWebhookMessage(BaseModel):
    id: str
    type: str
    text: Optional[str] = None
    contentProvider: Optional[Dict[str, Any]] = None


class LineWebhookEvent(BaseModel):
    type: str
    mode: Optional[str] = None
    timestamp: Optional[int] = None
    source: Optional[LineWebhookSource] = None
    replyToken: Optional[str] = None
    message: Optional[LineWebhookMessage] = None


class LineWebhookPayload(BaseModel):
    destination: Optional[str] = None
    events: List[LineWebhookEvent] = Field(default_factory=list)


class LineUserProfile(BaseModel):
    userId: str
    displayName: str
    pictureUrl: Optional[str] = None
    statusMessage: Optional[str] = None
    language: Optional[str] = None


class LineTextMessage(BaseModel):
    type: str = "text"
    text: str


class LineReplyRequest(BaseModel):
    replyToken: str
    messages: List[LineTextMessage]


class LinePushRequest(BaseModel):
    to: str
    messages: List[LineTextMessage]

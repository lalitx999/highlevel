import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.oauth import HLOAuthToken


class LINECredential(Base):
    __tablename__ = "line_credentials"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    location_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("hl_oauth_tokens.location_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    channel_secret: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    channel_access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    oauth_token: Mapped["HLOAuthToken"] = relationship(
        "HLOAuthToken",
        back_populates="line_credentials",
    )


class LINEReplyToken(Base):
    __tablename__ = "line_reply_tokens"

    line_user_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    reply_token: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ContactMapping(Base):
    __tablename__ = "contact_mappings"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    location_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    hl_contact_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    line_user_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    line_display_name: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
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

    __table_args__ = (
        UniqueConstraint("location_id", "line_user_id", name="unique_location_line_user"),
        Index("ix_contact_mappings_location_id", "location_id"),
        Index("ix_contact_mappings_hl_contact_id", "hl_contact_id"),
        Index("ix_contact_mappings_line_user_id", "line_user_id"),
    )

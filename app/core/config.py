import os
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    PORT: int = Field(default=3000, description="Server port")
    NODE_ENV: Literal["development", "production", "test"] = Field(
        default="development", description="Application environment"
    )
    BASE_URL: str = Field(
        default="http://localhost:3000", description="Base URL of application"
    )

    # HighLevel App Credentials
    GHL_CLIENT_ID: str = Field(default="", description="GHL OAuth Client ID")
    GHL_CLIENT_SECRET: str = Field(default="", description="GHL OAuth Client Secret")
    GHL_SCOPES: str = Field(
        default="contacts.readonly contacts.write conversations.readonly conversations.write conversations/message.readonly conversations/message.write",
        description="GHL OAuth Scopes",
    )
    GHL_REDIRECT_URI: str = Field(
        default="http://localhost:3000/api/oauth/callback",
        description="GHL OAuth Redirect URI",
    )
    GHL_BASE_URL: str = Field(
        default="https://services.leadconnectorhq.com",
        description="HighLevel API Base URL",
    )
    GHL_CONVERSATION_PROVIDER_ID: str = Field(
        default="6ac0bbc0e2328b5346d36789",
        description="HighLevel Conversation Provider ID",
    )

    # LINE OA Credentials
    LINE_CHANNEL_ID: str = Field(default="", description="LINE Channel ID")
    LINE_CHANNEL_SECRET: str = Field(default="", description="LINE Channel Secret")
    LINE_CHANNEL_ACCESS_TOKEN: str = Field(
        default="", description="LINE Channel Access Token"
    )
    LINE_BASE_URL: str = Field(
        default="https://api.line.me/v2/bot",
        description="LINE Messaging API Base URL",
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/line_ghl_poc?schema=public",
        description="PostgreSQL Connection URL",
    )

    @property
    def async_database_url(self) -> str:
        """Ensure the URL uses the asyncpg driver scheme for SQLAlchemy."""
        url = self.DATABASE_URL
        # Remove query parameters like schema=public if needed or let asyncpg handle it
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        # Strip ?schema=... if present because asyncpg doesn't accept schema as a direct URL param
        if "?schema=" in url:
            base, query = url.split("?schema=", 1)
            # If there are other query params after &
            if "&" in query:
                other_params = query.split("&", 1)[1]
                url = f"{base}?{other_params}"
            else:
                url = base
        return url


settings = Settings()

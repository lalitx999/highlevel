import time
from datetime import datetime, timezone
from typing import Dict, NamedTuple, Optional
from sqlalchemy import delete, select
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.models.line import LINEReplyToken


class CachedToken(NamedTuple):
    reply_token: str
    expires_at_ms: float


class ReplyTokenStore:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self._cache: Dict[str, CachedToken] = {}
        self._ttl_ms: float = ttl_seconds * 1000.0

    async def set(self, line_user_id: str, reply_token: str) -> None:
        """Save a replyToken for a given LINE user ID (60s TTL) in memory and DB."""
        now_ms = time.time() * 1000.0
        expires_at_ms = now_ms + self._ttl_ms
        expires_at_dt = datetime.fromtimestamp(expires_at_ms / 1000.0, tz=timezone.utc)

        # 1. Update in-memory cache
        self._cache[line_user_id] = CachedToken(
            reply_token=reply_token,
            expires_at_ms=expires_at_ms,
        )

        # 2. Async DB persistence
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(LINEReplyToken).where(LINEReplyToken.line_user_id == line_user_id)
                res = await session.execute(stmt)
                db_token = res.scalar_one_or_none()

                if db_token:
                    db_token.reply_token = reply_token
                    db_token.expires_at = expires_at_dt
                else:
                    db_token = LINEReplyToken(
                        line_user_id=line_user_id,
                        reply_token=reply_token,
                        expires_at=expires_at_dt,
                    )
                    session.add(db_token)
                await session.commit()
        except Exception as exc:
            logger.warn(
                f"Failed to persist replyToken to database; using in-memory cache: {exc}",
                lineUserId=line_user_id,
            )

    async def get(self, line_user_id: str) -> Optional[str]:
        """Get valid replyToken for line_user_id. Returns None if expired or non-existent."""
        now_ms = time.time() * 1000.0
        cached = self._cache.get(line_user_id)

        if cached:
            if cached.expires_at_ms > now_ms:
                return cached.reply_token
            else:
                self._cache.pop(line_user_id, None)

        # DB Fallback lookup
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(LINEReplyToken).where(LINEReplyToken.line_user_id == line_user_id)
                res = await session.execute(stmt)
                db_token = res.scalar_one_or_none()

                if db_token:
                    expires_at = db_token.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    now_dt = datetime.now(timezone.utc)

                    if expires_at > now_dt:
                        # Hydrate in-memory cache
                        exp_ms = expires_at.timestamp() * 1000.0
                        self._cache[line_user_id] = CachedToken(
                            reply_token=db_token.reply_token,
                            expires_at_ms=exp_ms,
                        )
                        return db_token.reply_token
                    else:
                        # Cleanup expired DB record
                        await session.delete(db_token)
                        await session.commit()
        except Exception as exc:
            logger.warn(
                f"Failed to query replyToken from database: {exc}",
                lineUserId=line_user_id,
            )

        return None

    async def invalidate(self, line_user_id: str) -> None:
        """Invalidate replyToken after it has been used."""
        self._cache.pop(line_user_id, None)
        try:
            async with AsyncSessionLocal() as session:
                stmt = delete(LINEReplyToken).where(LINEReplyToken.line_user_id == line_user_id)
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.warn(
                f"Failed to delete replyToken from database: {exc}",
                lineUserId=line_user_id,
            )


reply_token_store = ReplyTokenStore()

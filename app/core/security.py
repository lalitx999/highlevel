import base64
import hashlib
import hmac
from typing import Optional
from app.core.config import settings
from app.core.logging import logger


def verify_line_signature(
    raw_body: bytes,
    signature: Optional[str],
    channel_secret: Optional[str] = None,
) -> bool:
    """
    Verify LINE Webhook signature using HMAC-SHA256 and constant-time string comparison.
    """
    secret = channel_secret or settings.LINE_CHANNEL_SECRET
    if not signature:
        logger.warn("Missing x-line-signature header", error_code="LINE_SIG_MISSING")
        return False

    if not secret:
        logger.warn(
            "LINE Channel Secret is not configured",
            error_code="LINE_SECRET_MISSING",
        )
        return False

    try:
        hash_digest = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
        computed_signature = base64.b64encode(hash_digest).decode("utf-8")

        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(computed_signature, signature)
        if not is_valid:
            logger.warn(
                "Invalid x-line-signature header",
                error_code="LINE_SIG_INVALID",
            )
        return is_valid
    except Exception as exc:
        logger.error(
            f"Error verifying LINE signature: {exc}",
            error_code="LINE_SIG_VERIFY_ERROR",
        )
        return False

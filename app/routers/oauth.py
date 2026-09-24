import base64
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.schemas.highlevel import GHLTokenResponse
from app.services.ghl_token_manager import ghl_token_manager

router = APIRouter(prefix="/api/oauth", tags=["OAuth"])


def _decode_jwt_payload(jwt_token: str) -> dict:
    """Safely decode JWT payload without verification to extract claims."""
    try:
        parts = jwt_token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        # Fix padding if necessary
        remainder = len(payload_b64) % 4
        if remainder > 0:
            payload_b64 += "=" * (4 - remainder)
        decoded_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception as exc:
        logger.warn(f"Failed to decode JWT access token claims: {exc}")
        return {}


@router.get("/callback", summary="HighLevel OAuth Callback")
async def handle_ghl_callback(
    code: Optional[str] = Query(None, description="OAuth authorization code"),
    locationId: Optional[str] = Query(None, description="Location ID in query params"),
):
    """
    Handles OAuth Authorization Code callback from GoHighLevel.
    Exchanges code for access & refresh tokens and stores them safely in PostgreSQL.
    """
    if not code:
        logger.warn("Missing code parameter in OAuth callback", error_code="OAUTH_CODE_MISSING")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code parameter",
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.GHL_BASE_URL}/oauth/token",
                data={
                    "client_id": settings.GHL_CLIENT_ID,
                    "client_secret": settings.GHL_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.GHL_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
            token_response = GHLTokenResponse(**data)

        # Multi-Tier Fallback for locationId:
        # Tier 1: Body payload
        resolved_location_id = token_response.locationId

        # Tier 2: Query parameter
        if not resolved_location_id and locationId:
            resolved_location_id = locationId

        # Tier 3: Decode JWT access_token claims
        if not resolved_location_id:
            jwt_claims = _decode_jwt_payload(token_response.access_token)
            resolved_location_id = (
                jwt_claims.get("locationId")
                or jwt_claims.get("location_id")
                or jwt_claims.get("sub")
            )
            if resolved_location_id:
                logger.info(
                    "Resolved locationId from JWT access_token claims",
                    locationId=resolved_location_id,
                )

        if not resolved_location_id:
            logger.error("Could not resolve locationId from any tier in OAuth callback")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to resolve locationId from OAuth response",
            )

        # Save tokens
        await ghl_token_manager.save_tokens(token_response, resolved_location_id)

        logger.info(
            "HighLevel OAuth connection successful",
            locationId=resolved_location_id,
        )

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <title>Authorization Successful</title>
            <style>
              body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: #0f172a;
                color: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
              }}
              .card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 40px;
                text-align: center;
                max-width: 480px;
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
              }}
              h1 {{ color: #22c55e; margin-bottom: 12px; }}
              p {{ color: #94a3b8; font-size: 15px; line-height: 1.5; }}
              .badge {{
                display: inline-block;
                background: #0284c7;
                color: white;
                padding: 4px 10px;
                border-radius: 6px;
                font-weight: 600;
                font-family: monospace;
              }}
            </style>
          </head>
          <body>
            <div class="card">
              <h1>HighLevel Authorization Successful!</h1>
              <p>Your HighLevel Sub-Account (<span class="badge">{resolved_location_id}</span>) has been successfully connected to the LINE OA Middleware.</p>
            </div>
          </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"HighLevel OAuth code exchange failed: {exc}",
            error_code="OAUTH_EXCHANGE_FAILED",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth Authorization failed: {exc}",
        )

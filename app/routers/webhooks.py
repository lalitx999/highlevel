import json
import time
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_trace_id, logger, set_trace_id
from app.core.security import verify_line_signature
from app.models.contact import ContactMapping
from app.models.oauth import HLOAuthToken
from app.schemas.common import OutboundWebhookResult, StandardResponse
from app.schemas.highlevel import (
    GHLCreateContactPayload,
    GHLInboundMessagePayload,
    GHLOutboundWebhookPayload,
)
from app.schemas.line import LineWebhookEvent, LineWebhookPayload
from app.services.ghl_api import ghl_api_service
from app.services.line_api import line_api_service
from app.services.reply_token_store import reply_token_store

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


async def _get_default_location_id() -> Optional[str]:
    """Retrieve the latest active location_id from the database."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(HLOAuthToken.location_id).order_by(desc(HLOAuthToken.updated_at)).limit(1)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()
    except Exception as exc:
        logger.error(f"Error looking up default HighLevel locationId: {exc}")
        return None


async def process_line_inbound_events(
    raw_body: bytes,
    query_location_id: Optional[str],
    trace_id: str,
) -> None:
    """
    Background Task: Process inbound LINE webhook events asynchronously without blocking HTTP response.
    """
    set_trace_id(trace_id)
    start_time = time.time()

    try:
        payload_dict = json.loads(raw_body.decode("utf-8"))
        payload = LineWebhookPayload(**payload_dict)
    except Exception as exc:
        logger.error(f"Failed to parse LINE Webhook payload: {exc}", error_code="LINE_PAYLOAD_PARSE_ERR")
        return

    if not payload.events:
        logger.debug("LINE Webhook received empty events list")
        return

    default_location_id = await _get_default_location_id()

    for event in payload.events:
        # Process text message events only
        if event.type != "message" or not event.message or event.message.type != "text":
            continue

        line_user_id = event.source.userId if event.source else None
        message_text = event.message.text
        reply_token = event.replyToken

        if not line_user_id or not message_text:
            logger.warn("Received text message event missing userId or text", event=event.model_dump())
            continue

        try:
            # 1. Cache replyToken with 60-second TTL
            if reply_token:
                await reply_token_store.set(line_user_id, reply_token)
                logger.info("Cached LINE replyToken (60s TTL)", lineUserId=line_user_id, replyToken=reply_token)

            location_id = query_location_id or default_location_id
            if not location_id:
                logger.error(
                    "No HighLevel locationId found in system. Please complete OAuth flow first.",
                    error_code="LOCATION_ID_MISSING",
                    lineUserId=line_user_id,
                )
                continue

            # 2. Contact De-duplication: Query contact_mappings table
            hl_contact_id: Optional[str] = None
            async with AsyncSessionLocal() as session:
                stmt = select(ContactMapping).where(
                    ContactMapping.location_id == location_id,
                    ContactMapping.line_user_id == line_user_id,
                )
                res = await session.execute(stmt)
                mapping = res.scalar_one_or_none()
                if mapping:
                    hl_contact_id = mapping.hl_contact_id

            if not hl_contact_id:
                # Check GHL API directly before creating new contact
                existing_ghl_contact = await ghl_api_service.find_contact_by_line_user_id(
                    location_id, line_user_id
                )

                if existing_ghl_contact:
                    hl_contact_id = existing_ghl_contact.id
                    # Store mapping in DB
                    async with AsyncSessionLocal() as session:
                        new_mapping = ContactMapping(
                            location_id=location_id,
                            hl_contact_id=hl_contact_id,
                            line_user_id=line_user_id,
                            line_display_name=existing_ghl_contact.firstName,
                        )
                        session.add(new_mapping)
                        await session.commit()
                    logger.info("Linked existing GHL contact to LINE User", lineUserId=line_user_id, hlContactId=hl_contact_id)
                else:
                    # Fetch LINE user profile
                    profile = await line_api_service.get_user_profile(line_user_id)

                    # Create new HighLevel Contact
                    created_contact = await ghl_api_service.create_contact(
                        GHLCreateContactPayload(
                            locationId=location_id,
                            firstName=profile.displayName,
                            customFields=[{"key": "line_user_id", "value": line_user_id}],
                        )
                    )
                    hl_contact_id = created_contact.id

                    # Save mapping to database
                    async with AsyncSessionLocal() as session:
                        new_mapping = ContactMapping(
                            location_id=location_id,
                            hl_contact_id=hl_contact_id,
                            line_user_id=line_user_id,
                            line_display_name=profile.displayName,
                        )
                        session.add(new_mapping)
                        await session.commit()
                    logger.info(
                        "Created new GHL contact and mapping",
                        lineUserId=line_user_id,
                        hlContactId=hl_contact_id,
                        displayName=profile.displayName,
                    )

            # 3. Inject inbound message into HighLevel Conversations API
            provider_id = settings.GHL_CONVERSATION_PROVIDER_ID or None
            await ghl_api_service.inject_inbound_message(
                location_id,
                GHLInboundMessagePayload(
                    type="SMS",
                    contactId=hl_contact_id,
                    message=message_text,
                    conversationProviderId=provider_id,
                ),
            )

            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Inbound message processed from LINE to HighLevel successfully",
                lineUserId=line_user_id,
                hlContactId=hl_contact_id,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Failed to process inbound LINE message: {exc}",
                error_code="INBOUND_LINE_PROCESSING_FAILED",
                lineUserId=line_user_id,
                latency_ms=latency_ms,
                exc_info=True,
            )


@router.get("/line", summary="LINE Webhook Health/Info")
async def line_webhook_info():
    return {
        "status": "active",
        "message": "LINE Webhook endpoint is online.",
        "notice": "Please send HTTP POST requests with a valid x-line-signature header from LINE Messaging API Platform.",
    }


@router.post("/line", summary="LINE Inbound Webhook")
async def handle_line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: Optional[str] = Header(None, alias="x-line-signature"),
    locationId: Optional[str] = Query(None, description="Optional HighLevel locationId"),
):
    """
    Receives incoming webhook events from LINE Messaging API.
    Verifies HMAC-SHA256 signature, responds HTTP 200 immediately, and delegates processing to BackgroundTasks.
    """
    raw_body = await request.body()

    # 1. Signature Verification
    if not verify_line_signature(raw_body, x_line_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing x-line-signature",
        )

    # 2. Fast Non-blocking return with BackgroundTasks
    trace_id = get_trace_id() or ""
    background_tasks.add_task(
        process_line_inbound_events,
        raw_body=raw_body,
        query_location_id=locationId,
        trace_id=trace_id,
    )

    return {"status": "ok"}


@router.get("/highlevel/outbound", summary="HighLevel Outbound Webhook Health/Info")
@router.get("/highlevel/provider-outbound", summary="HighLevel Provider Outbound Webhook Health/Info")
async def ghl_outbound_webhook_info():
    return {
        "status": "active",
        "message": "HighLevel Outbound Webhook endpoint is online.",
        "notice": "Please send HTTP POST requests from HighLevel Provider Webhook.",
    }


@router.post("/highlevel/outbound", response_model=OutboundWebhookResult, summary="HighLevel Outbound Webhook")
@router.post("/highlevel/provider-outbound", response_model=OutboundWebhookResult, summary="HighLevel Provider Outbound Webhook")
async def handle_ghl_outbound_webhook(payload: GHLOutboundWebhookPayload):
    """
    Receives outbound message events from HighLevel CRM when an agent sends a message.
    Reroutes message to LINE using Reply API (if <60s TTL token exists) or Push API.
    """
    start_time = time.time()

    # 1. Strict Echo Suppression: Ignore inbound events or received echoes
    direction_str = payload.get_direction_string().lower()
    type_str = (payload.type or "").lower()
    status_str = (payload.status or "").lower()

    is_inbound = (
        direction_str == "inbound"
        or "inbound" in type_str
        or status_str == "received"
    )

    if is_inbound:
        logger.info(
            "Ignoring inbound message echo from HighLevel webhook",
            direction=direction_str,
            type=type_str,
            status=status_str,
        )
        return OutboundWebhookResult(status="ignored", reason="inbound_echo_suppressed")

    # If direction is explicitly set and not outbound/sms, ignore
    if direction_str and direction_str not in ("outbound", "sms"):
        logger.info("Ignoring non-outbound GHL webhook event", direction=direction_str)
        return OutboundWebhookResult(status="ignored", reason="not_outbound")

    contact_id = payload.get_contact_id()
    message_body = payload.get_message_text()
    location_id = payload.get_location_id()

    if not contact_id or not message_body:
        logger.warn("GHL Outbound Webhook missing contactId or message body", payload=payload.model_dump())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload: contactId and body/message are required",
        )

    # 2. Query contact_mappings table by hl_contact_id
    async with AsyncSessionLocal() as session:
        query = select(ContactMapping).where(ContactMapping.hl_contact_id == contact_id)
        if location_id:
            query = query.where(ContactMapping.location_id == location_id)
        res = await session.execute(query)
        mapping = res.scalar_one_or_none()

    if not mapping:
        logger.warn(
            "No matching LINE user found for HighLevel contact ID",
            error_code="CONTACT_MAPPING_NOT_FOUND",
            contactId=contact_id,
            locationId=location_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contact mapping found for given contactId",
        )

    line_user_id = mapping.line_user_id

    # 3. Check for valid Reply Token (<60s TTL)
    valid_reply_token = await reply_token_store.get(line_user_id)
    delivery_method = "PUSH"

    try:
        if valid_reply_token:
            try:
                await line_api_service.send_reply(valid_reply_token, message_body)
                delivery_method = "REPLY"
                # Invalidate single-use token immediately
                await reply_token_store.invalidate(line_user_id)
            except Exception as reply_err:
                logger.warn(
                    f"Reply API failed (token may have expired or been rejected): {reply_err}. Falling back to Push API...",
                    lineUserId=line_user_id,
                )
                await line_api_service.send_push(line_user_id, message_body)
                delivery_method = "PUSH"
        else:
            # Token expired or not found -> Send via Push API
            await line_api_service.send_push(line_user_id, message_body)
            delivery_method = "PUSH"

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Outbound message dispatched from HighLevel to LINE user successfully",
            contactId=contact_id,
            lineUserId=line_user_id,
            deliveryMethod=delivery_method,
            latency_ms=latency_ms,
        )

        return OutboundWebhookResult(
            status="success",
            deliveryMethod=delivery_method,
            lineUserId=line_user_id,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"Failed to dispatch outbound message to LINE: {exc}",
            error_code="OUTBOUND_LINE_DELIVERY_FAILED",
            contactId=contact_id,
            lineUserId=line_user_id,
            latency_ms=latency_ms,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deliver message to LINE: {exc}",
        )

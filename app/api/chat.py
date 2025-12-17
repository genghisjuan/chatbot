from __future__ import annotations

import json
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.core.bot import process_chat_stream
from app.schemas import (
    CallbackRequest,
    ChatInput,
    FeedbackInput,
    InboundCallRequest,
    Message,
    SupportRequest,
)
from app.services import logger
from app.services.analytics import AnalyticsService
from app.services.email_service import EmailService

router = APIRouter()

# Image validation helper (replaces deprecated imghdr)
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB limit


def validate_image_bytes(image_data: bytes) -> Optional[str]:
    """Check image format from magic bytes. Returns format or None."""
    if image_data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_data.startswith(b"GIF87a") or image_data.startswith(b"GIF89a"):
        return "gif"
    if image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
        return "webp"
    return None


# Dependency injection for services (singleton pattern)
_analytics_service: Optional[AnalyticsService] = None
_email_service: Optional[EmailService] = None


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def _parse_conversation_history(conversation_history: str) -> List[Message]:
    """
    Parse conversation_history JSON into Message objects.
    
    If STRICT_HISTORY_VALIDATION is enabled, enforces structural limits to prevent DoS.
    """
    from app.core.config import settings
    
    try:
        history_data = json.loads(conversation_history)
    except json.JSONDecodeError as e:
        detail = f"Invalid JSON in conversation_history: {e}" if not settings.SANITIZE_ERRORS else "Invalid conversation history format"
        raise HTTPException(status_code=400, detail=detail)
    
    # SECURITY: Strict validation (opt-in via config)
    if settings.STRICT_HISTORY_VALIDATION:
        if not isinstance(history_data, list):
            raise HTTPException(status_code=400, detail="conversation_history must be a JSON array")
        
        if len(history_data) > 100:  # Prevent pathological payloads
            raise HTTPException(status_code=400, detail="conversation_history exceeds maximum length (100 messages)")
        
        for idx, item in enumerate(history_data):
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail=f"Message at index {idx} must be an object")
            
            if "role" not in item or "content" not in item:
                raise HTTPException(status_code=400, detail=f"Message at index {idx} missing required fields")
            
            if not isinstance(item.get("content"), str):
                raise HTTPException(status_code=400, detail=f"Message content at index {idx} must be a string")
            
            if len(item.get("content", "")) > 10000:  # Per-message limit
                raise HTTPException(status_code=400, detail=f"Message at index {idx} exceeds maximum length")
    
    try:
        return [Message(**msg) for msg in history_data]
    except (TypeError, KeyError, ValidationError) as e:
        detail = f"Invalid message format: {e}" if not settings.SANITIZE_ERRORS else "Invalid message structure"
        raise HTTPException(status_code=400, detail=detail)


async def _read_and_validate_image_upload(file: UploadFile) -> bytes:
    """
    Read image bytes with stream-capped reading and enforce type/size/content checks.
    
    SECURITY: Stream-capped read prevents memory exhaustion from unbounded file.read().
    This maintains existing behavior (same 413 error) but protects against exploitation.
    """
    from app.core.config import settings
    
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        detail = (
            f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
            if not settings.SANITIZE_ERRORS  
            else "Unsupported file type"
        )
        raise HTTPException(status_code=400, detail=detail)

    # SECURITY: Stream-capped read (always active for defense-in-depth)
    # Read incrementally to prevent memory exhaustion while maintaining existing semantics
    chunks = []
    total_bytes = 0
    chunk_size = 8192  # 8KB chunks
    
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        
        total_bytes += len(chunk)
        if total_bytes > MAX_IMAGE_BYTES:
            # Same error message as before, but prevented memory exhaustion
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
        
        chunks.append(chunk)
    
    image_bytes = b"".join(chunks)

    actual_type = validate_image_bytes(image_bytes)
    if actual_type not in ["jpeg", "png", "gif", "webp"]:
        detail = "Invalid or corrupted image file" if not settings.SANITIZE_ERRORS else "Invalid image file"
        raise HTTPException(status_code=400, detail=detail)

    return image_bytes


@router.post("/chat")
async def chat_endpoint(
    user_message: str = Form(..., min_length=1, max_length=5000),
    conversation_history: str = Form(default="[]", max_length=50000),
    language: str = Form(default="en-US", pattern=r"^[a-z]{2}(-[A-Z]{2})?$"),
    mode: str = Form(default="chat", pattern=r"^(chat|deal)$"),  # NEW: mode parameter
    file: UploadFile = File(None),
):
    try:
        history_objs = _parse_conversation_history(conversation_history)

        chat_input = ChatInput(
            user_message=user_message,
            conversation_history=history_objs,
            language=language,
        )

        image_bytes = None
        if file:
            image_bytes = await _read_and_validate_image_upload(file)

        # Query logging is now handled in bot.py to capture is_fallback status
        return StreamingResponse(
            process_chat_stream(chat_input, image_bytes=image_bytes, mode=mode),  # Pass mode to bot
            media_type="text/plain",
        )
    except HTTPException:
        raise  # Re-raise HTTPExceptions as-is
    except Exception as e:
        # SECURITY: Error sanitization (opt-in via config)
        # Server logs ALWAYS contain full details regardless of flag
        from app.core.config import settings
        
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        
        if settings.SANITIZE_ERRORS:
            # Production-safe: hide implementation details
            raise HTTPException(status_code=500, detail="Internal server error")
        else:
            # Development/debugging: preserve original behavior
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/trending")
async def get_trending_topics(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    try:
        # Get top topics from last 24 hours (returns list of dicts with label, count, prompt)
        trending = await analytics_service.get_trending_topics(hours=24)
        return {"topics": trending}
    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch trending topics")


@router.post("/feedback")
async def feedback_endpoint(
    feedback: FeedbackInput,
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    try:
        # Log to file (existing behavior)
        logger.log_interaction(
            "user",
            "FEEDBACK",
            f"MessageID: {feedback.message_id} | Rating: {feedback.rating}",
            success=True,
        )

        # Also store in database with context for analytics
        if feedback.user_query and feedback.bot_response:
            analytics_service.log_feedback(
                user_query=feedback.user_query,
                bot_response=feedback.bot_response,
                rating=feedback.rating,
                message_id=feedback.message_id,
            )

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Feedback endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/support/email")
async def support_email_endpoint(
    request: SupportRequest,
    email_service: EmailService = Depends(get_email_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    try:
        ticket_id = await email_service.send_support_email(
            request.name,
            request.business,
            request.summary,
            request.conversation_history,
        )

        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate ticket")

        logger.log_interaction(
            "user",
            "SUPPORT_REQUEST",
            f"Email sent for {request.name} ({request.business}) - Ticket: {ticket_id}",
            success=True,
        )

        # Log analytics
        analytics_service.log_escalation("email")
        return {"status": "success", "ticket_id": ticket_id}
    except Exception as e:
        logger.log_interaction("user", "SUPPORT_REQUEST_FAIL", str(e), success=False)
        logger.error(f"Support email endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit support request")


@router.post("/support/callback")
async def support_callback_endpoint(
    request: CallbackRequest,
    email_service: EmailService = Depends(get_email_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    try:
        ticket_id = await email_service.send_callback_request(
            request.phone,
            request.preferred_time,
            request.conversation_history,
        )

        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate callback ticket")

        logger.log_interaction(
            "user",
            "CALLBACK_REQUEST",
            f"Callback requested for {request.phone} - Ticket: {ticket_id}",
            success=True,
        )

        # Log analytics
        analytics_service.log_escalation("callback")
        return {"status": "success", "ticket_id": ticket_id}
    except Exception as e:
        logger.log_interaction("user", "CALLBACK_REQUEST_FAIL", str(e), success=False)
        logger.error(f"Callback endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit callback request")


@router.post("/support/call-inbound")
async def inbound_call_endpoint(
    request: InboundCallRequest,
    email_service: EmailService = Depends(get_email_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    try:
        ticket_id = await email_service.create_inbound_call_ticket(
            request.phone,
            request.conversation_history,
        )

        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate inbound call ticket")

        logger.log_interaction(
            "user",
            "INBOUND_CALL_INIT",
            f"Inbound call initiated from {request.phone} - Ticket: {ticket_id}",
            success=True,
        )

        # Log analytics
        analytics_service.log_escalation("call-inbound")
        return {"status": "success", "ticket_id": ticket_id}
    except Exception as e:
        logger.log_interaction("user", "INBOUND_CALL_FAIL", str(e), success=False)
        logger.error(f"Inbound call endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process inbound call request")

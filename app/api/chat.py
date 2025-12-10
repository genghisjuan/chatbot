from fastapi import APIRouter, HTTPException, Form, File, UploadFile, Depends
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from app.schemas import ChatInput, Message, FeedbackInput, SupportRequest, CallbackRequest, InboundCallRequest
from app.core.bot import process_chat_stream
from app.services.analytics import AnalyticsService
from app.services import logger
from app.services.email_service import EmailService
import json

router = APIRouter()

# Image validation helper (replaces deprecated imghdr)
def validate_image_bytes(image_data: bytes) -> str:
    """Check image format from magic bytes. Returns format or None."""
    if image_data.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
        return 'gif'
    elif image_data.startswith(b'RIFF') and image_data[8:12] == b'WEBP':
        return 'webp'
    return None

# Dependency injection for services (singleton pattern)
_analytics_service = None
_email_service = None

def get_analytics_service():
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service

def get_email_service():
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service

@router.post("/chat")
async def chat_endpoint(
    user_message: str = Form(..., min_length=1, max_length=5000),
    conversation_history: str = Form(default="[]", max_length=50000),
    language: str = Form(default="en-US", pattern=r"^[a-z]{2}(-[A-Z]{2})?$"),
    file: UploadFile = File(None)
):
    try:
        # Parse conversation history from JSON string
        try:
            history_data = json.loads(conversation_history)
            history_objs = [Message(**msg) for msg in history_data]
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in conversation_history: {e}")
        except (TypeError, KeyError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid message format: {e}")

        # Construct ChatInput object
        chat_input = ChatInput(
            user_message=user_message,
            conversation_history=history_objs,
            language=language
        )

        # Read image bytes if file is provided
        image_bytes = None
        if file:
            # Validate file type from header
            allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(allowed_types)}"
                )
            
            # Read file and validate size
            image_bytes = await file.read()
            if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
                raise HTTPException(status_code=413, detail="File too large (max 10MB)")
            
            # Verify actual image content (magic bytes)
            actual_type = validate_image_bytes(image_bytes)
            if actual_type not in ['jpeg', 'png', 'gif', 'webp']:
                raise HTTPException(status_code=400, detail="Invalid or corrupted image file")

        # Query logging is now handled in bot.py to capture is_fallback status
        
        return StreamingResponse(
            process_chat_stream(chat_input, image_bytes=image_bytes), 
            media_type="text/plain"
        )
    except HTTPException:
        raise  # Re-raise HTTPExceptions as-is
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/trending")
async def get_trending_topics(
    analytics_service: AnalyticsService = Depends(get_analytics_service)
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
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    try:
        # Log to file (existing behavior)
        logger.log_interaction(
            "user", 
            "FEEDBACK", 
            f"MessageID: {feedback.message_id} | Rating: {feedback.rating}", 
            success=True
        )
        
        # Also store in database with context for analytics
        if feedback.user_query and feedback.bot_response:
            analytics_service.log_feedback(
                user_query=feedback.user_query,
                bot_response=feedback.bot_response,
                rating=feedback.rating
            )
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Feedback endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/support/email")
async def support_email_endpoint(
    request: SupportRequest,
    email_service: EmailService = Depends(get_email_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    try:
        ticket_id = await email_service.send_support_email(
            request.name, 
            request.business, 
            request.summary, 
            request.conversation_history
        )
        
        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate ticket")
             
        logger.log_interaction(
            "user", 
            "SUPPORT_REQUEST", 
            f"Email sent for {request.name} ({request.business}) - Ticket: {ticket_id}", 
            success=True
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
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    try:
        ticket_id = await email_service.send_callback_request(
            request.phone, 
            request.preferred_time, 
            request.conversation_history
        )
        
        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate callback ticket")

        logger.log_interaction(
            "user", 
            "CALLBACK_REQUEST", 
            f"Callback requested for {request.phone} - Ticket: {ticket_id}", 
            success=True
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
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    try:
        ticket_id = await email_service.create_inbound_call_ticket(
            request.phone, 
            request.conversation_history
        )
        
        if not ticket_id or not ticket_id.strip():
            raise Exception("Failed to generate inbound call ticket")

        logger.log_interaction(
            "user", 
            "INBOUND_CALL_INIT", 
            f"Inbound call initiated from {request.phone} - Ticket: {ticket_id}", 
            success=True
        )
        
        # Log analytics
        analytics_service.log_escalation("call-inbound")
        return {"status": "success", "ticket_id": ticket_id}
    except Exception as e:
        logger.log_interaction("user", "INBOUND_CALL_FAIL", str(e), success=False)
        logger.error(f"Inbound call endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process inbound call request")


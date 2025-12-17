"""
Deal Assistant API Routes
Completely separate from chatbot routes
Handles discovery questions and battle card generation
"""
from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
from app.core.deal_bot import get_deal_assistant

# Create router with /api/v1/deal prefix
router = APIRouter(prefix="/api/v1/deal", tags=["deal"])


class DealChatResponse(BaseModel):
    """Response model for deal assistant chat"""
    response: str


@router.post("/chat", response_model=DealChatResponse)
async def deal_chat(
    user_message: str = Form(...),
    conversation_history: str = Form("[]"),
    language: str = Form("en-US"),
    mode: str = Form(None)  # Optional, for compatibility
):
    """
    Unified deal assistant endpoint
    Handles both question generation and battle card creation
    
    Accepts FormData (multipart/form-data) to match existing frontend
    
    Args:
        user_message: User's message/request
        conversation_history: JSON string of conversation history
        language: Language code (default: en-US)
        mode: Optional mode parameter (ignored, for compatibility)
    
    Returns:
        DealChatResponse with AI response (JSON for questions/battlecard)
    
    Examples:
        - "Generate all 3 guided questions. Context: {vertical: restaurant}"
          → Returns JSON with questions array
        - "Generate battle card" (with Q&A in conversation_history)
          → Returns JSON with battle card structure
    """
    try:
        # Parse conversation history from JSON string
        try:
            history = json.loads(conversation_history)
        except:
            history = []
        
        # Get singleton deal assistant instance
        deal_assistant = get_deal_assistant()
        
        # Call dedicated deal brain
        response_text = await deal_assistant.chat(
            user_message=user_message,
            conversation_history=history
        )
        
        return DealChatResponse(response=response_text)
    
    except Exception as e:
        # Log error and return 500
        print(f"Error in deal_chat: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Deal Assistant error: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for Deal Assistant
    Returns status of deal brain
    """
    try:
        deal_assistant = get_deal_assistant()
        return {
            "status": "healthy",
            "service": "JUNA Deal Assistant",
            "model": deal_assistant.model,
            "version": "v2.1-separated"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# Optional: Dedicated endpoints for specific functions
# (Currently using unified /chat, but these could be separated later)

@router.post("/questions")
async def generate_questions(
    user_message: str = Form(...),
    language: str = Form("en-US")
):
    """
    Dedicated endpoint to generate 3 discovery questions
    (Alternative to unified /chat endpoint)
    
    Args:
        user_message: Context in user_message field
        language: Language code
    
    Returns:
        JSON with questions array
    """
    try:
        deal_assistant = get_deal_assistant()
        response_text = await deal_assistant.generate_questions(user_message)
        return DealChatResponse(response=response_text)
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Question generation error: {str(e)}"
        )


@router.post("/battlecard")
async def generate_battlecard(
    conversation_history: str = Form("[]"),
    language: str = Form("en-US")
):
    """
    Dedicated endpoint to generate battle card
    (Alternative to unified /chat endpoint)
    
    Args:
        conversation_history: JSON string of full conversation history with Q&A
        language: Language code
    
    Returns:
        JSON with battle card structure
    """
    try:
        # Parse conversation history
        try:
            history = json.loads(conversation_history)
        except:
            history = []
        
        deal_assistant = get_deal_assistant()
        response_text = await deal_assistant.generate_battlecard(
            conversation_history=history
        )
        return DealChatResponse(response=response_text)
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Battle card generation error: {str(e)}"
        )

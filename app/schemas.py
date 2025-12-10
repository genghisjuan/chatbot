from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
import re

# Shared validator function
def _validate_phone_number(v: str, allow_unknown: bool = False) -> str:
    """Shared phone validation logic"""
    if allow_unknown and v == "Unknown":
        return v
    cleaned = re.sub(r'[\s\-\(\)\.]', '', v)
    if not cleaned.isdigit() or len(cleaned) < 10 or len(cleaned) > 15:
        raise ValueError('Phone must contain 10-15 digits')
    return cleaned

class Message(BaseModel):
    """Single message in a conversation"""
    role: str
    content: str

class ChatInput(BaseModel):
    """User input for chat endpoint"""
    user_message: str = Field(..., min_length=1, max_length=2000, description="User's question or message")
    conversation_history: List[Message] = Field(default_factory=list)
    user_id: Optional[str] = None
    language: str = "en-US"

class ChatOutput(BaseModel):
    """Assistant response from chat endpoint"""
    assistant_message: str
    actions: Optional[List[str]] = None

class FeedbackInput(BaseModel):
    """User feedback on a bot response"""
    message_id: str
    rating: Literal["up", "down"]  # Only "up" or "down" allowed
    user_query: Optional[str] = None
    bot_response: Optional[str] = None
    comment: Optional[str] = Field(None, max_length=1000)

class SupportRequest(BaseModel):
    """Request to escalate to human support via email"""
    name: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    business: str = Field(..., min_length=1, max_length=200, strip_whitespace=True)
    summary: str = Field(..., min_length=10, max_length=2000, strip_whitespace=True)
    conversation_history: Optional[List[Message]] = None

class CallbackRequest(BaseModel):
    """Request for support team to call back"""
    phone: str = Field(..., min_length=10, max_length=20, description="Phone number (10-15 digits)")
    preferred_time: str = Field(..., min_length=3, max_length=100, description="Preferred callback time")
    conversation_history: Optional[List[Message]] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        return _validate_phone_number(v, allow_unknown=False)

class InboundCallRequest(BaseModel):
    """Request triggered by inbound phone call"""
    phone: str = Field(default="Unknown", description="Caller's phone number")
    conversation_history: Optional[List[Message]] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        return _validate_phone_number(v, allow_unknown=True)

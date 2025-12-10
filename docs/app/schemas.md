# schemas.py - API Request/Response Models

## Overview

`schemas.py` defines Pydantic models that validate and serialize all API requests and responses for the Support Chatbot. These models ensure type safety, input validation, and automatic OpenAPI documentation generation.

## What This File Does

**Primary Responsibilities:**
1. Define request/response data structures for all API endpoints
2. Validate user input (string lengths, phone formats, allowed values)
3. Sanitize input (strip whitespace, normalize phone numbers)
4. Provide type hints for editor autocomplete
5. Auto-generate OpenAPI/Swagger documentation

## Models Overview

```
Chat System
├── Message - Single conversation message
├── ChatInput - User's chat request
└── ChatOutput - Assistant's response

Feedback System
└── FeedbackInput - User feedback (thumbs up/down)

Support Escalation
├── SupportRequest - Email support request
├── CallbackRequest - Request for callback
└── InboundCallRequest - Triggered by incoming call
```

## Model Documentation

### Message
```python
class Message(BaseModel):
    \"\"\"Single message in a conversation\"\"\"
    role: str  # "user" or "assistant"
    content: str  # Message text
```

**Purpose**: Represents one turn in a conversation (either user or assistant).

**Used by**: All models that track conversation history.

### ChatInput
```python
class ChatInput(BaseModel):
    \"\"\"User input for chat endpoint\"\"\"
    user_message: str  # 1-2000 characters
    conversation_history: List[Message]  # Previous messages
    user_id: Optional[str]  # For analytics
    language: str  # Default: "en-US"
```

**Validation**:
- `user_message`: Must be 1-2000 characters (prevents empty/spam messages)
- `conversation_history`: Uses `default_factory=list` to avoid mutable default bug

**Example**:
```json
{
  "user_message": "How do I reset my password?",
  "conversation_history": [],
  "user_id": "user123",
  "language": "en-US"
}
```

### ChatOutput
```python
class ChatOutput(BaseModel):
    \"\"\"Assistant response from chat endpoint\"\"\"
    assistant_message: str  # Bot's response
    actions: Optional[List[str]]  # Triggered actions (e.g., ["escalate"])
```

**Example**:
```json
{
  "assistant_message": "To reset your password, click...",
  "actions": null
}
```

### FeedbackInput
```python
class FeedbackInput(BaseModel):
    \"\"\"User feedback on a bot response\"\"\"
    message_id: str  # ID of message being rated
    rating: Literal["up", "down"]  # Only these values allowed
    user_query: Optional[str]  # Original question
    bot_response: Optional[str]  # Bot's answer
    comment: Optional[str]  # Max 1000 chars
```

**Validation**:
- `rating`: Type-safe - only accepts "up" or "down"
- `comment`: Limited to 1000 characters

**Example**:
```json
{
  "message_id": "msg_12345",
  "rating": "down",
  "comment": "Response was not helpful"
}
```

### SupportRequest
```python
class SupportRequest(BaseModel):
    \"\"\"Request to escalate to human support via email\"\"\"
    name: str  # 1-100 chars, whitespace stripped
    business: str  # 1-200 chars, whitespace stripped
    summary: str  # 10-2000 chars, whitespace stripped
    conversation_history: Optional[List[Message]]
```

**Validation**:
- All fields: Whitespace automatically stripped
- `name`: 1-100 characters (prevents empty/spam)
- `business`: 1-200 characters
- `summary`: 10-2000 characters (forces meaningful description)

**Example**:
```json
{
  "name": "John Smith",
  "business": "Acme Corp",
  "summary": "I need help with billing for account #12345"
}
```

### CallbackRequest
```python
class CallbackRequest(BaseModel):
    \"\"\"Request for support team to call back\"\"\"
    phone: str  # 10-15 digits, formatting removed
    preferred_time: str  # 3-100 chars (e.g., "2pm EST")
    conversation_history: Optional[List[Message]]
```

**Validation**:
- `phone`: Strips formatting (spaces, dashes, parentheses), validates 10-15 digits
- `preferred_time`: Min 3 characters (prevents spam)

**Phone Normalization**:
```python
Input:  "555-123-4567"
Output: "5551234567"

Input:  "(555) 123.4567"
Output: "5551234567"
```

### InboundCallRequest
```python
class InboundCallRequest(BaseModel):
    \"\"\"Request triggered by inbound phone call\"\"\"
    phone: str  # Default: "Unknown" (caller ID blocked)
    conversation_history: Optional[List[Message]]
```

**Validation**:
- Allows "Unknown" for blocked caller ID
- Otherwise validates 10-15 digits like `CallbackRequest`

## Shared Validators

### _validate_phone_number()
```python
def _validate_phone_number(v: str, allow_unknown: bool = False) -> str:
    \"\"\"Shared phone validation logic\"\"\"
    # Allow "Unknown" if caller ID blocked
    if allow_unknown and v == "Unknown":
        return v
    
    # Remove common formatting
    cleaned = re.sub(r'[\\s\\-\\(\\)\\.]', '', v)
    
    # Validate digits and length
    if not cleaned.isdigit() or len(cleaned) < 10 or len(cleaned) > 15:
        raise ValueError('Phone must contain 10-15 digits')
    
    return cleaned
```

**Used by**: `CallbackRequest`, `InboundCallRequest`

**Why shared?** Avoids code duplication, ensures consistent validation across models.

## Usage Examples

### Validating Chat Input
```python
from app.schemas import ChatInput

# Valid input
chat_input = ChatInput(
    user_message=\"How do I reset my password?\",
    conversation_history=[],
    user_id=\"user123\"
)

# Invalid input - raises ValidationError
try:
    ChatInput(user_message=\"\")  # Too short
except ValidationError as e:
    print(e)  # \"ensure this value has at least 1 characters\"
```

### Testing Phone Validation
```python
from app.schemas import CallbackRequest

# Valid phones (all normalized to digits)
CallbackRequest(phone=\"555-123-4567\", preferred_time=\"2pm\")  # ✓
CallbackRequest(phone=\"(555) 123 4567\", preferred_time=\"morning\")  # ✓
CallbackRequest(phone=\"5551234567\", preferred_time=\"anytime\")  # ✓

# Invalid phones - raise ValidationError
CallbackRequest(phone=\"123\", preferred_time=\"2pm\")  # Too short
CallbackRequest(phone=\"abc-def-ghij\", preferred_time=\"2pm\")  # Not digits
```

### Using in FastAPI Endpoints
```python
from fastapi import APIRouter
from app.schemas import ChatInput, ChatOutput

router = APIRouter()

@router.post(\"/chat\", response_model=ChatOutput)
async def chat(input: ChatInput):
    # Pydantic automatically validates input
    # If invalid, returns 422 Unprocessable Entity
    
    # Access validated fields
    message = input.user_message  # Guaranteed 1-2000 chars
    history = input.conversation_history  # Guaranteed list
    
    # Process and return
    return ChatOutput(
        assistant_message=\"Response\",
        actions=None
    )
```

## Validation Rules Summary

| Field | Min Length | Max Length | Special Validation |
|-------|-----------|------------|-------------------|
| `user_message` | 1 | 2000 | - |
| `rating` | - | - | Only "up" or "down" |
| `name` | 1 | 100 | Whitespace stripped |
| `business` | 1 | 200 | Whitespace stripped |
| `summary` | 10 | 2000 | Whitespace stripped |
| `comment` | 0 | 1000 | - |
| `phone` | 10 | 15 | Digits only, formatting removed |
| `preferred_time` | 3 | 100 | - |

## Security Features

1. **Input Length Limits**: Prevents DoS via large payloads
2. **Whitespace Stripping**: Prevents whitespace-only spam
3. **Phone Sanitization**: Removes potential injection characters
4. **Type Constraints**: `Literal` types prevent unexpected values
5. **Required Fields**: Uses `...` to enforce non-null values

## OpenAPI Integration

These models automatically generate OpenAPI documentation:

**Generated Swagger UI includes**:
- Field types and constraints
- Example values (if provided)
- Required vs optional fields
- Error response formats

**Access at**: `http://localhost:8000/docs` when server running

## Testing

### Unit Testing Models
```python
import pytest
from pydantic import ValidationError
from app.schemas import FeedbackInput

def test_feedback_rating_validation():
    # Valid ratings
    FeedbackInput(message_id=\"123\", rating=\"up\")  # ✓
    FeedbackInput(message_id=\"123\", rating=\"down\")  # ✓
    
    # Invalid rating
    with pytest.raises(ValidationError):
        FeedbackInput(message_id=\"123\", rating=\"invalid\")

def test_phone_normalization():
    req = CallbackRequest(phone=\"(555) 123-4567\", preferred_time=\"2pm\")
    assert req.phone == \"5551234567\"  # Formatted stripped
```

## Best Practices

### When Adding New Fields
1. **Always add validation**: Use `Field()` with constraints
2. **Provide descriptions**: Helps API consumers
3. **Consider security**: Could this accept malicious input?
4. **Add examples**: Improves generated docs

### When Modifying Existing Fields
1. **Check for breaking changes**: Will existing clients fail?
2. **Update tests**: Ensure validation still works
3. **Review dependent code**: What uses this model?

## Troubleshooting

### Issue: ValidationError on Valid Data
**Symptom**: Pydantic rejects data that looks correct  
**Cause**: Mismatch between client format and model expectations  
**Fix**: Check field types, ensure required fields present

### Issue: Phone Validation Failing
**Symptom**: `ValueError: Phone must contain 10-15 digits`  
**Cause**: Phone includes non-digit characters or wrong length  
**Fix**: 
- Check phone number format
- Ensure it's 10-15 digits after removing formatting
- For unknown caller ID, use "Unknown"

### Issue: Rating Not Constrained
**Symptom**: Analytics shows unexpected rating values  
**Cause**: Old code using `str` instead of `Literal`  
**Fix**: Already fixed - rating is now `Literal["up", "down"]`

## File Dependencies

- **Pydantic**: Core validation library
- **Typing**: Type hints (List, Optional, Literal)
- **re**: Regular expressions for phone validation
- **Used by**: All API endpoints in `app/api/`

## Related Documentation

- [Pydantic Validation](https://docs.pydantic.dev/latest/concepts/validators/)
- [FastAPI Models](https://fastapi.tiangolo.com/tutorial/body/)
- [docs/app/api/chat.md](./api/chat.md) - Chat endpoint implementation


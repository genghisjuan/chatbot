# Bot Core Documentation

## Overview

**File**: [`app/core/bot.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/core/bot.py)

The Bot Core module implements the main conversational AI pipeline using RAG (Retrieval Augmented Generation) with CRAG (Corrective RAG) enhancements. This is the heart of the chatbot - where user messages are processed, knowledge is retrieved, and AI responses are generated.

---

## Table of Contents

1. [Summary](#summary)
2. [Architecture](#architecture)
3. [Processing Pipeline](#processing-pipeline)
4. [Functions](#functions)
5. [CRAG Pipeline](#crag-pipeline)
6. [Vision Mode](#vision-mode)
7. [Token Tracking](#token-tracking)
8. [Configuration](#configuration)
9. [Security](#security)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Summary

This module provides **1 main async generator function** that powers the entire chat experience:

| Function | Purpose | Returns |
|----------|---------|---------|
| `process_chat_stream()` | Process user message through RAG pipeline | Async generator yielding response chunks |

**Key Features**:
- ✅ **Streaming responses** for better UX (immediate feedback)
- ✅ **CRAG pipeline** for improved answer accuracy
- ✅ **Vision support** (GPT-4o handles images)
- ✅ **Security-first** with prompt injection detection
- ✅ **Accurate cost tracking** using tiktoken
- ✅ **Multi-language support** (13 languages)
- ✅ **Context-aware** query rewriting for conversations

---

## Architecture

### Service Initialization Pattern

```python
# Lazy singleton pattern prevents premature initialization
_kb = None
_analytics = None
_vision_client = None

def get_kb():
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
```

**Why Lazy Initialization?**
- Allows testing with mocks
- Defers expensive operations until needed
- Enables proper configuration before initialization
- Prevents circular dependencies

### Data Flow

```
User Message
    ↓
1. Security Check (injection detection)
    ↓
2. Branch: Image? → Vision Mode (GPT-4o)
           No Image? ↓
3. Query Contextualization (history-aware)
    ↓
4. Knowledge Base Retrieval (Pinecone)
    ↓
5. CRAG Grading (correct/ambiguous/incorrect)
    ↓
6. Knowledge Refining (optional)
    ↓
7. LLM Response Generation (streaming)
    ↓
8. Analytics Logging (tokens, feedback)
```

---

## Processing Pipeline

### 1. Input Sanitization

```python
clean_message = security.sanitize_input(chat_input.user_message)
```

**Purpose**: Remove potentially harmful characters, normalize whitespace

### 2. Security Checks

```python
if security.detect_injection(clean_message):
    logger.log_security_event("PROMPT_INJECTION", ...)
    yield "I cannot fulfill that request due to security policies."
    return
```

**Detection Methods**:
- Jailbreak phrase detection
- Suspicious instruction patterns
- Role manipulation attempts

### 3. Vision Mode (If Image Provided)

**Trigger**: `image_bytes` parameter is not None

**Behavior**:
1. Validate image size (≤ 10MB)
2. Base64 encode image
3. Call GPT-4o vision API
4. Stream response directly
5. **Bypass RAG pipeline entirely**

### 4. Query Contextualization

**Purpose**: Make follow-up questions understandable without conversation history

**Example**:
```
History:
  User: "How do I reset my terminal?"
  AI: "Press the red button for 5 seconds..."
  
Current Question: "What if that doesn't work?"

Rewritten Query: "What if pressing the red button for 5 seconds doesn't reset the terminal?"
```

**Model Used**: `gpt-4o-mini` (cheap, fast)

### 5. Knowledge Retrieval

```python
kb_results = await get_kb().search(search_query, k=5)
```

**Returns**: Top 5 most relevant document chunks from Pinecone

**Metadata Included**:
- Source filename
- Page number
- Relevance score

### 6. CRAG Grading

```python
grade = await grader.grade_documents(clean_message, context)
```

**Possible Grades**:
| Grade | Meaning | Action |
|-------|---------|--------|
| `correct` | KB highly relevant | Use KB, refine it |
| `ambiguous` | KB somewhat relevant | Use KB, refine it (fail open) |
| `incorrect` | KB not relevant | Discard KB, empty context |

**Helper Function**:
```python
def should_use_kb_context(grade: str) -> bool:
    return grade in ["correct", "ambiguous"]
```

### 7. Knowledge Refining

```python
if should_use_kb_context(grade):
    context = await refiner.refine_knowledge(clean_message, context)
```

**Purpose**: Clean up retrieved text, remove irrelevant parts, highlight key info

### 8. LLM Response Generation

**Model**: `gpt-4o`

**System Prompt**: 70-line detailed persona (JUNA, Payroc support assistant)

**Streaming**: Yields chunks as they arrive for real-time UX

### 9. Analytics Logging

**Token Counting** (accurate with tiktoken):
```python
input_tokens = len(_encoder.encode(message_text))
output_tokens = len(_encoder.encode(full_response))
embedding_tokens = len(_encoder.encode(clean_message))
```

**Logged Data**:
- User query
- Is initial message? (conversation start)
- Is fallback? (KB grade != "correct")
- Token counts for cost tracking

---

## Functions

### process_chat_stream()

```python
async def process_chat_stream(
    chat_input: ChatInput,
    image_bytes: bytes | None = None
) -> AsyncGenerator[str, None]:
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `chat_input` | ChatInput | Yes | Pydantic model with user message, history, language |
| `image_bytes` | bytes \| None | No | Optional image for vision mode |

**Returns**: `AsyncGenerator[str, None]` - Streams response text chunks

**Usage Example**:
```python
chat_input = ChatInput(
    user_message="How do I reset my terminal?",
    conversation_history=[],
    language="en-US",
    user_id="user_123"
)

async for chunk in process_chat_stream(chat_input):
    print(chunk, end="", flush=True)
```

**With Image**:
```python
with open("terminal_error.jpg", "rb") as f:
    image_bytes = f.read()

async for chunk in process_chat_stream(chat_input, image_bytes):
    print(chunk, end="")
```

---

### Helper Functions

#### should_use_kb_context()

```python
def should_use_kb_context(grade: str) -> bool:
    """Determine if KB context should be used based on CRAG grade."""
    return grade in ["correct", "ambiguous"]
```

**Purpose**: Encapsulate CRAG decision logic

#### get_kb(), get_analytics(), get_vision_client()

**Purpose**: Lazy singleton getters for services

**Pattern**:
```python
def get_service():
    global _service
    if _service is None:
        _service = Service()
    return _service
```

---

## CRAG Pipeline

### What is CRAG?

**Corrective RAG** adds a grading step to traditional RAG:

**Traditional RAG**:
```
Query → Retrieve → Generate Response
```

**CRAG**:
```
Query → Retrieve → Grade Relevance → 
  ├─ Correct: Use KB
  ├─ Ambiguous: Refine & Use KB
  └─ Incorrect: Discard KB (or web search, disabled here)
```

### Why CRAG?

**Problem**: Traditional RAG sometimes retrieves irrelevant documents

**Examples**:
- User asks about "apple" (fruit), KB returns Apple Inc. documentation
- Query too vague, retrieves random content
- Technical jargon mismatch

**Solution**: Grade documents before using them

### Grading Process

**Document Grader**:
```python
grader = DocumentGrader()
grade = await grader.grade_documents(question, context)
```

**LLM Prompt** (simplified):
```
Given this question and retrieved documents, are the documents relevant?
- "correct": Directly answers question
- "ambiguous": Partially relevant
- "incorrect": Not relevant at all
```

### Knowledge Refiner

**Purpose**: Clean up noisy KB chunks

**Refiner Actions**:
- Remove irrelevant sentences
- Highlight key facts
- Reorder for clarity
- Remove duplicate info

---

## Vision Mode

### Activation

Vision mode activates when `image_bytes` is provided and non-empty.

### Validation

1. **Size Check**: ≤ 10MB (constant `MAX_IMAGE_SIZE`)
2. **Early Rejection**: Returns error message if too large

### Processing

```python
client = get_vision_client()  # Singleton AsyncOpenAI
image_b64 = base64.b64encode(image_bytes).decode('utf-8')

response = await client.chat.completions.create(
    model=VISION_MODEL,  # "gpt-4o"
    messages=[
        {"role": "system", "content": "...vision prompt..."},
        {"role": "user", "content": [
            {"type": "text", "text": clean_message},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
        ]}
    ],
    stream=True
)
```

### Vision System Prompt

**Scope**: Only payment processing, POS systems, terminals

**Rejection Examples**:
- Cat photos
- Random screenshots unrelated to payments
- Non-business content

**Acceptance Examples**:
- Terminal error messages
- Receipt issues
- Hardware photos

---

## Token Tracking

### Why Accurate Tracking Matters

**Problem**: OpenAI charges by token, not character

**Naive Approach** (inaccurate):
```python
tokens ≈ len(text) // 4  # Can be off by 2-3x!
```

**Correct Approach** (tiktoken):
```python
encoder = tiktoken.encoding_for_model("gpt-4")
tokens = len(encoder.encode(text))
```

### Token Types Tracked

| Token Type | Source | Purpose |
|------------|--------|---------|
| **Input** | User message + system prompt + history | LLM API cost |
| **Output** | AI response | LLM API cost |
| **Embedding** | User query (embedding API) | Pinecone search cost |

### Cost Calculation

**OpenAI Pricing** (as of Dec 2024, gpt-4o):
- Input: $0.0025 per 1K tokens
- Output: $0.01 per 1K tokens  
- Embeddings: $0.00002 per 1K tokens

**Example**:
```
Input: 500 tokens → $0.00125
Output: 200 tokens → $0.002
Embeddings: 50 tokens → $0.000001
Total: ~$0.003 per query
```

---

## Configuration

### Constants

```python
MAX_HISTORY_MESSAGES = 4  # Include last 4 messages in context
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
VISION_MODEL = "gpt-4o"
CHAT_MODEL = "gpt-4o"
CONTEXT_MODEL = "gpt-4o-mini"  # Cheap model for query rewriting
```

### Language Support

13 languages supported via `LANGUAGE_MAP`:

```python
LANGUAGE_MAP = {
    "en-US": "English",
    "es-ES": "Spanish",
    "fr-FR": "French",
    "de-DE": "German",
    "zh-CN": "Simplified Chinese",
    # ... 8 more
}
```

**Usage**: System prompt instructs AI to respond in selected language

---

## Security

### 1. Prompt Injection Detection

```python
if security.detect_injection(clean_message):
    yield "I cannot fulfill that request due to security policies."
    return
```

**Protected Patterns**:
- "Ignore previous instructions"
- "You are now..."
- Role manipulation
- System prompt extraction attempts

### 2. Input Sanitization

**Purpose**: Remove dangerous characters, normalize whitespace

### 3. Error Message Security

**Before (unsafe)**:
```python
yield f"Error: {str(e)}"  # Leaks internal details!
```

**After (safe)**:
```python
logger.error(f"Error: {e}", exc_info=True)  # Log internally
yield "I encountered an error. Please try again."  # Generic to user
```

### 4. Image Size Limits

**Protection**: Prevents DoS via huge image uploads

---

## Best Practices

### 1. Always Use Lazy Getters

**✅ Good**:
```python
kb = get_kb()
analytics = get_analytics()
```

**❌ Bad**:
```python
kb = KnowledgeBase()  # Creates new instance!
```

### 2. Stream Responses

**✅ Good**: Use `async for` to yield chunks immediately

**❌ Bad**: Accumulate full response before returning

**Why**: Streaming provides instant feedback, better UX

### 3. Log Errors with Context

**✅ Good**:
```python
logger.error(f"Vision error for user {user_id}: {e}", exc_info=True)
```

**❌ Bad**:
```python
print(f"Error: {e}")  # No context, no traceback
```

### 4. Catch Specific Exceptions

**✅ Good**:
```python
except OpenAIError as e:
    # Handle API errors
except Exception as e:
    # Catch-all for unexpected
```

**❌ Bad**:
```python
except Exception:  # Too broad, masks bugs
```

---

## Troubleshooting

### Issue: Inaccurate cost tracking
**Cause**: tiktoken not installed or encoder not initialized  
**Solution**: `pip install tiktoken`

### Issue: Vision mode fails with "Image too large"
**Cause**: Image exceeds 10MB  
**Solution**: Compress image client-side before upload

### Issue: CRAG always grades "incorrect"
**Cause**: KB documents not relevant to domain  
**Solution**: Re-index KB with better documents

### Issue: Responses not streaming
**Cause**: Not using `async for` or buffering somewhere  
**Solution**: Verify streaming all the way from LLM to client

### Issue: "Lazy service not initialized" error
**Cause**: Calling service directly instead of getter  
**Solution**: Use `get_kb()` not `kb` (which is None)

### Issue: Multi-language responses in English
**Cause**: `language` parameter not passed correctly  
**Solution**: Verify `ChatInput.language` is set (e.g. "es-ES")

---

## Performance Considerations

### Singleton Pattern Impact

**Before** (new services per request):
- Each request: ~500ms overhead (DB connection, Pinecone init)
- 100 requests/min: +50 seconds total

**After** (singleton lazy init):
- First request: ~500ms overhead
- Subsequent: ~0ms overhead
- 100 requests/min: +0.5 seconds total

**Improvement**: ~100x faster!

### Token Counting Overhead

**tiktoken encoding**: ~1ms per 1K tokens

**Trade-off**: Minimal latency for accurate cost tracking

### Streaming Benefits

**Time to first token**: ~500ms (vision), ~300ms (chat)

**User Perception**: Instant response vs. 5+ second wait

---

## Related Documentation

- [Chat API](../api/chat.md) - REST endpoints that call this module
- [Knowledge Base](../services/kb.md) - Pinecone retrieval details
- [CRAG Components](../services/crag.md) - Grader & Refiner implementation
- [Security Module](./security.md) - Input sanitization & injection detection


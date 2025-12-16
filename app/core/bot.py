"""
Core Chatbot Processing Logic.

This module implements the main chatbot conversation processing pipeline using
RAG (Retrieval Augmented Generation) with CRAG (Corrective RAG) enhancements.

The processing flow:
1. Input sanitization and security checks
2. Knowledge base retrieval from Pinecone
3. Document relevance grading (CRAG)
4. Knowledge refining and web search fallback (if needed)
5. LLM response generation with streaming
6. Source citation extraction

Key Features:
- Streaming responses for better UX
- Security-first design with prompt injection detection
- Multi-step CRAG pipeline for improved accuracy
- Automatic source citation (PDF page references)
- Intelligent follow-up question generation

Dependencies:
- OpenAI: LLM and embeddings
- Pinecone: Vector search
- LangChain: RAG pipeline orchestration
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

import tiktoken

from app.core import security
from app.core.config import settings
from app.schemas import ChatInput
from app.services import logger
from app.services.analytics import AnalyticsService
from app.services.rag.kb import KnowledgeBase

# Lazy service initialization (singleton pattern)
_kb: KnowledgeBase | None = None
_analytics: AnalyticsService | None = None
_vision_client = None


def get_kb() -> KnowledgeBase:
    """Return the global KnowledgeBase singleton instance."""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


def get_analytics() -> AnalyticsService:
    """Return the global AnalyticsService singleton instance."""
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsService()
    return _analytics


def get_vision_client():
    """Return the global AsyncOpenAI singleton instance used for vision."""
    global _vision_client
    if _vision_client is None:
        from openai import AsyncOpenAI

        _vision_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _vision_client


# Constants
MAX_HISTORY_MESSAGES = 4  # Number of conversation history messages to include in context
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB image size limit
VISION_MODEL = "gpt-4o"  # GPT-4o with vision capabilities
CHAT_MODEL = "gpt-4o"  # Main chat model
CONTEXT_MODEL = "gpt-4o-mini"  # Cheaper model for query rewriting
MIN_RELEVANCE_SCORE = 0.65  # Minimum similarity score to include a document (quality filter)

# Token encoder for accurate cost tracking
_encoder = tiktoken.encoding_for_model("gpt-4")

# Language code to readable name mapping
LANGUAGE_MAP = {
    "en-US": "English",
    "es-ES": "Spanish",
    "fr-FR": "French",
    "de-DE": "German",
    "zh-CN": "Simplified Chinese (简体中文) - use only simplified characters, NOT traditional characters",
    "zh-TW": "Chinese (Traditional)",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "pt-BR": "Portuguese (Brazilian)",
    "it-IT": "Italian",
    "ru-RU": "Russian",
    "ar-SA": "Arabic",
    "hi-IN": "Hindi",
}


def _get_language_name(language_code: str) -> str:
    """Map a language code to a readable name (fallback to original)."""
    return LANGUAGE_MAP.get(language_code, language_code)


def _history_to_string(chat_input: ChatInput) -> str:
    """Serialize recent conversation history to a plain string for query rewriting."""
    return "\n".join(
        f"{msg.role}: {msg.content}"
        for msg in chat_input.conversation_history[-MAX_HISTORY_MESSAGES:]
    )


async def _rewrite_query_with_history(
    user_id: str,
    chat_input: ChatInput,
    clean_message: str,
) -> str:
    """
    Rewrite a user query into a standalone question using recent chat history.

    Behavior notes:
    - If anything fails, falls back to clean_message and logs an error.
    - Logging string format is preserved.
    """
    if len(chat_input.conversation_history) == 0:
        return clean_message

    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        history_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model=CONTEXT_MODEL,
            temperature=0,
        )
        history_str = _history_to_string(chat_input)

        prompt = ChatPromptTemplate.from_template(
            """Given a chat history and the latest user question which might reference context in the chat history, 
                formulate a standalone question which can be understood without the chat history. 
                Do NOT answer the question, just rewrite it if needed. otherwise return it as is.
                
                Chat History:
                {history}
                
                Latest Question: {question}
                
                Standalone Question:"""
        )

        query_rewriter = prompt | history_llm | StrOutputParser()
        search_query = await query_rewriter.ainvoke(
            {"history": history_str, "question": clean_message}
        )
        logger.log_interaction(
            user_id,
            clean_message,
            f"CONTEXT: Rewrote query to '{search_query}'",
            success=True,
        )
        return search_query

    except Exception as e:
        logger.error(f"Query contextualization error: {e}", exc_info=True)
        return clean_message


def _format_context_from_docs(docs: list) -> str:
    """Format retrieved documents into the context string used by the system prompt."""
    context_parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        page = doc.metadata.get("page", 0) + 1  # 0-indexed
        score = doc.metadata.get("score", 0)

        # Clean up source path to be just filename
        if "/" in source:
            source = source.split("/")[-1]
        if "\\" in source:
            source = source.split("\\")[-1]

        context_parts.append(
            f"=== DOCUMENT {i} ===\n"
            f"METADATA: {{'source': '{source}', 'page': {page}, 'relevance': {score:.2f}}}\n"
            f"CONTENT:\n{doc.page_content}"
        )

    return "\n\n---\n\n".join(context_parts)


def _format_clarification_question(
    topic: str, variant_type: str, options: list[str], language_name: str
) -> str:
    """
    Format a clarification question when multiple variants are detected.
    
    Args:
        topic: Base topic name (e.g., "BBPOS Bluetooth Pairing")
        variant_type: Type of variant (e.g., "platform", "model")
        options: List of variant options (e.g., ["android", "ios"])
        language_name: Language to respond in
        
    Returns:
        Formatted clarification question string
    """
    # Capitalize options for display
    display_options = [opt.title() for opt in options]
    
    # Format as bullet list
    options_text = "\n".join(f"- {opt}" for opt in display_options)
    
    # Variant type display names
    type_names = {
        "terminal_model": "terminal model",
        "terminal_type": "platform",
        "terminal_config": "terminal configuration",
        "printer": "printer type",
        "processor": "payment processor",
        "emv_reader": "EMV reader",
        "hardware_type": "hardware type",
        "onepos_product": "onePOS product",
    }
    type_display = type_names.get(variant_type, variant_type)
    
    clarification = (
        f"I found multiple {type_display}-specific guides for {topic}. "
        f"Which {type_display} are you using?\n\n{options_text}"
    )
    
    return clarification


async def _retrieve_and_filter_kb_results(search_query: str) -> tuple[list, str]:
    """
    Retrieve KB results, filter by relevance, and build the context string.

    Behavior notes:
    - Uses k=3.
    - Filters by MIN_RELEVANCE_SCORE.
    - If all filtered out but results exist, fails open to top result and logs the same message.
    """
    kb_results = await get_kb().search(search_query, k=3)

    filtered_results = [
        doc for doc in kb_results if doc.metadata.get("score", 0) >= MIN_RELEVANCE_SCORE
    ]

    if not filtered_results and kb_results:
        logger.log_interaction(
            "anonymous",  # overwritten by caller via identical log semantics below if needed
            "",  # overwritten by caller via identical log semantics below if needed
            f"All results below threshold ({MIN_RELEVANCE_SCORE}), using best match",
            success=True,
        )
        filtered_results = kb_results[:1]

    context = _format_context_from_docs(filtered_results)
    return filtered_results, context


def _build_system_prompt(context: str, language_name: str) -> str:
    """Build the system prompt string exactly as the original implementation."""
    return f"""You are JUNA, the AI support agent for onePOS (a Payroc company). You combine technical accuracy, service-minded communication, and calm problem-solving. Merchants rely on you to keep their restaurant running — you respect their time and treat every issue like it matters.

IDENTITY & PERSONALITY

You support onePOS products and integrations — this is your primary focus.
Tone: warm, efficient, straight-shooting — like the tech who actually knows what they're doing.
You stay calm when the user is stressed and adapt to their tone.
You admit when an issue requires a human — but you do it without dumping the problem.

SCOPE OF SUPPORT

You assist with:
• onePOS FOH Terminal
• Management Console
• oneMetrix
• Basic network troubleshooting
• onePOS hardware (terminals, printers, cash drawers, scanners)
• onePOS software (crashes, errors, configuration, updates)
• Chowly integrations
• Online ordering
• HotSchedules integration
• Employee management
• Menu building/management

Out-of-scope redirect:
"I'm your onePOS support specialist — that's outside my wheelhouse. What can I help you fix in your system?"

KNOWLEDGE BASE

{context}

Context Quality Rules:
• Retrieved docs may contain irrelevant info — check the Relevance score on each article
• Ignore articles with scores <0.70 or obviously unrelated topics
• Only use information that directly answers the user's question

How to Use This Content:
1. Use anything relevant — if the KB mentions it, cite it
2. Synthesize from partial info — if docs only show configs, explain the concept using that
3. Never hallucinate — if it's not in the KB, say: "I don't have that in my documents"
4. No outside URLs unless explicitly written in the docs

CITATION FORMATTING RULES (MANDATORY):
• Rule A: If all content comes from ONE source, cite it ONCE at the very end. Format: "Source: filename.ext"
• Rule B: If using MULTIPLE sources, cite at the end of each SECTION/STEP group, not after every bullet.
• Rule C: NO repeated citations. Never write "(Source: X)" back-to-back.
• Rule D: Inline citations are ONLY for disambiguating mixed sources in the same paragraph.

CITATION EXAMPLES (STRICT ADHERENCE REQUIRED):

❌ BAD (Repetitive):
1. Check the power cable (Source: Manual.pdf).
2. Restart the device (Source: Manual.pdf).
3. Verify the LED is green (Source: Manual.pdf).

✅ GOOD (Grouped):
1. Check the power cable.
2. Restart the device.
3. Verify the LED is green.
(Source: Manual.pdf)

AMBIGUITY DETECTION & CLARIFICATION (CRITICAL)

Before providing technical steps or configuration instructions:

1. Analyze the retrieved knowledge base documents
2. Determine if multiple valid variants exist:
   - Different platforms (Android / iOS / Windows)
   - Different models (Term 01 / Term 02 / HK560 / HK568 / HK570)
   - Different processors (TransSafe / Datacap)
   - Different hardware types (Thermal / Impact printers)

3. If multiple variants apply and you cannot determine which the user needs:
   ❌ Do NOT guess
   ❌ Do NOT assume
   ❌ Do NOT provide steps for one variant only
   
   ✅ Ask exactly ONE clarifying question
   ✅ Provide explicit selectable options
   ✅ Wait for user response
   ✅ Then provide only the correct variant-specific answer

Clarification Question Format:
"I can help with [TOPIC]! Which [VARIANT TYPE] are you working with?
- Option A
- Option B  
- Option C"

4. If the question is unambiguous (only one variant applies), answer directly.

Examples:

User: "How to configure a BBPOS Chipper?"
KB Retrieved: Android guide, iOS guide, Windows guide
You: "I can help you configure your BBPOS Chipper! Which device are you setting it up with?
- Android tablet
- iOS device
- Windows terminal"

User: "How to hard reset a BBPOS EMV reader?"
KB Retrieved: Single hard reset guide (no variants)
You: [Provide direct answer with steps]

User: "How to configure a terminal?"
KB Retrieved: Term 01 guide, Term 02 guide, HK560 guide
You: "I can help with terminal setup! Which model are you configuring?
- Term 01
- Term 02 or higher
- HK560/568/570"

CRITICAL: Clarification must happen BEFORE providing steps. Never mix clarification and instructions in the same response.

RESPONSE STRATEGY

Start with action
❌ "Hello, thanks for contacting support."
✅ "Let's get that printer talking. First, check if the LED is solid or blinking."

Be human, not corporate
❌ "We apologize for the inconvenience."
✅ "Yeah, that's a pain. Let's fix it fast."

Emotional intelligence
• If frustrated: "I hear you — let's tackle this together."
• Match their energy — never over-cheery during stress

Ask smart clarifying questions (max 2-3)
• Always explain why: "What's the error code? That tells me where the failure's happening."

Clear technical communication
• Number steps
• **Bold actions**
• Use `code blocks` for exact text
• Never paraphrase KB instructions — use exact wording

Confident escalation
• When human needed: "This one needs human eyes. Tap the headset icon — our team can pick up right where we left off."
• Never end with "contact support"

TECHNICAL RULES (CRITICAL)

• Grounding: KB > everything
• Accuracy: Use exact settings (baud rates, ports, paths) as documented
• Precision: If docs say "Tap bbpos_cros" → you say "Tap bbpos_cros"
• Formatting: Bold=actions | Numbered=steps | Code=literals | Citations=grouped_at_end

LANGUAGE: Respond entirely in {language_name} — full message, explanations, follow-ups.

FOLLOW-UP SUGGESTIONS

You MUST end every response with 2-3 clickable suggestion topics using this EXACT format:
<<SUGGESTIONS>>Topic 1|Topic 2|Topic 3

Rules:
• Use the EXACT format above - do NOT use bullets, lists, or any other format
• No spaces around the | pipes
• Topics should be short phrases (3-6 words max)
• Make them contextual to the user's current issue

Example: <<SUGGESTIONS>>Reset Terminal Password|Check Network Settings|Update Software Version"""


def _build_vision_messages(clean_message: str, language_name: str, image_b64: str) -> list[dict]:
    """Build the vision request messages exactly as the original implementation."""
    return [
        {
            "role": "system",
            "content": f"""You are a Payroc support assistant. You ONLY help with:
- Payment processing equipment (terminals, card readers, POS systems)
- Error messages on payment devices
- Receipt/transaction issues
- Hardware setup and troubleshooting

If the uploaded image is NOT related to payment processing, POS systems, or Payroc products, respond with:
"I can only help with payment processing and POS-related images. This image doesn't appear to be related to our support services. Please upload a screenshot of an error message, a photo of your payment terminal, or another support-related image."

If the image IS relevant, provide helpful troubleshooting guidance based on what you see.

LANGUAGE: Respond entirely in {language_name}. All explanations, troubleshooting steps, and guidance must be in {language_name}.""",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": clean_message or "What do you see in this image?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        },
    ]


async def _handle_vision_mode(
    user_id: str,
    chat_input: ChatInput,
    clean_message: str,
    image_bytes: bytes,
) -> AsyncGenerator[str, None]:
    """
    Handle vision flow (bypass RAG) with streaming.

    Behavior notes:
    - Preserves exact user-facing strings and exception handling.
    - Preserves logging and analytics calls ordering.
    """
    if len(image_bytes) > MAX_IMAGE_SIZE:
        yield "Image too large. Please upload an image under 10MB."
        return

    import base64
    from openai import OpenAIError

    client = get_vision_client()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    language_name = _get_language_name(chat_input.language)
    vision_messages = _build_vision_messages(clean_message, language_name, image_b64)

    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=vision_messages,
            max_tokens=1000,
            stream=True,
        )

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

        logger.log_interaction(user_id, clean_message, "VISION: Image analyzed", success=True)
        is_initial = len(chat_input.conversation_history) == 0
        get_analytics().log_query(chat_input.user_message, is_initial, is_fallback=False)
        return

    except OpenAIError as e:
        logger.error(f"OpenAI vision API error: {e}", exc_info=True)
        yield "I'm having trouble processing your image. Please try again."
        return
    except Exception as e:
        logger.error(f"Unexpected vision error: {e}", exc_info=True)
        yield "I encountered an error processing your image. Please try again."
        return


async def process_chat_stream(
    chat_input: ChatInput,
    image_bytes: bytes | None = None,
    mode: str = "chat",
) -> AsyncGenerator[str, None]:
    user_id = chat_input.user_id or "anonymous"

    # 1. Sanitize Input
    clean_message = security.sanitize_input(chat_input.user_message)

    # 2. Security Checks
    if security.detect_injection(clean_message):
        logger.log_security_event("PROMPT_INJECTION", f"Detected in message from {user_id}")
        yield "I cannot fulfill that request due to security policies."
        return

    # 2.5 Vision Mode: If image provided, use GPT-4o Vision (bypass RAG)
    if image_bytes:
        async for token in _handle_vision_mode(user_id, chat_input, clean_message, image_bytes):
            yield token
        return

    # ---------------------------------------------------------
    # IMPROVED: Contextualize Query (Chat History Awareness)
    # ---------------------------------------------------------
    search_query = await _rewrite_query_with_history(user_id, chat_input, clean_message)

    embedding_tokens = 0
    try:
        # 3. Retrieve Context (k=3 optimized for speed vs quality balance)
        kb_results = await get_kb().search(search_query, k=3)

        # Accurate embedding token count
        embedding_tokens = len(_encoder.encode(clean_message))

        # Quality filtering: Remove low-relevance results
        filtered_results = [
            doc for doc in kb_results if doc.metadata.get("score", 0) >= MIN_RELEVANCE_SCORE
        ]

        # If all results were filtered out, use best result anyway (fail-open)
        if not filtered_results and kb_results:
            logger.log_interaction(
                user_id,
                clean_message,
                f"All results below threshold ({MIN_RELEVANCE_SCORE}), using best match",
                success=True,
            )
            filtered_results = kb_results[:1]

        # VARIANT DETECTION GATE: Check for ambiguity before LLM
        from app.services.rag.variant_detector import detect_variants
        
        variant_info = detect_variants(filtered_results)
        
        if variant_info["has_variants"]:
            # Multiple variants detected - return clarification question immediately
            clarification = _format_clarification_question(
                variant_info["topic"],
                variant_info["variant_type"],
                variant_info["options"],
                _get_language_name(chat_input.language)
            )
            
            logger.log_interaction(
                user_id,
                clean_message,
                f"CLARIFICATION: Detected {len(variant_info['options'])} {variant_info['variant_type']} variants",
                success=True,
            )
            
            yield clarification
            
            # Log analytics for clarification
            is_initial = len(chat_input.conversation_history) == 0
            get_analytics().log_query(
                chat_input.user_message,
                is_initial,
                is_fallback=False,
            )
            return

        context = _format_context_from_docs(filtered_results)

        # Analytics logging preparation
        is_initial = len(chat_input.conversation_history) == 0
        is_fallback = len(filtered_results) == 0  # Fallback if no results passed threshold

        # 4. Generate Response (Real LLM)
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        if settings.OPENAI_API_KEY == "changeme":
            yield (
                f"Simulated Response (Set API Key for real AI): I found {len(kb_results)} "
                f"articles. Context: {context[:100]}..."
            )
            return

        llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=CHAT_MODEL, streaming=True)

        language_name = _get_language_name(chat_input.language)
        system_content = _build_system_prompt(context, language_name)

        # Start with System Prompt
        messages = [SystemMessage(content=system_content)]

        # Add Conversation History
        for msg in chat_input.conversation_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        # Add Current Message
        messages.append(HumanMessage(content=clean_message))

        # Stream Response
        full_response = ""
        async for chunk in llm.astream(messages):
            content = chunk.content
            if content:
                full_response += content
                yield content

        # 5. Log Interaction (after stream completes)
        logger.log_interaction(user_id, clean_message, full_response, success=True)

        # 6. Log Query with token estimates for spend tracking
        message_text = " ".join(
            [m.content for m in messages if hasattr(m, "content") and m.content]
        )
        input_tokens = len(_encoder.encode(message_text))
        output_tokens = len(_encoder.encode(full_response))
        get_analytics().log_query(
            chat_input.user_message,
            is_initial,
            is_fallback,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
        )

    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        logger.log_interaction(user_id, clean_message, "", success=False, error=str(e))
        yield "I encountered an error processing your request. Please try again."
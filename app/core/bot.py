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
from app.schemas import ChatInput
from app.core import security
from app.services.rag.kb import KnowledgeBase
from app.core.config import settings
from app.services import logger
from app.services.analytics import AnalyticsService
from typing import AsyncGenerator
import tiktoken

# Lazy service initialization (singleton pattern)
_kb = None
_analytics = None
_vision_client = None

def get_kb():
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb

def get_analytics():
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsService()
    return _analytics

def get_vision_client():
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
    "hi-IN": "Hindi"
}



async def process_chat_stream(chat_input: ChatInput, image_bytes: bytes | None = None, mode: str = "chat") -> AsyncGenerator[str, None]:
    user_id = chat_input.user_id or "anonymous"
    
    # DEAL MODE vs CHAT MODE distinction
    is_deal_mode = (mode == "deal")
    # 1. Sanitize Input
    clean_message = security.sanitize_input(chat_input.user_message)
    
    # 2. Security Checks
    if security.detect_injection(clean_message):
        logger.log_security_event("PROMPT_INJECTION", f"Detected in message from {user_id}")
        yield "I cannot fulfill that request due to security policies."
        return
    
    # 2.5 Vision Mode: If image provided, use GPT-4o Vision (bypass RAG)
    if image_bytes:
        # Validate image size
        if len(image_bytes) > MAX_IMAGE_SIZE:
            yield "Image too large. Please upload an image under 10MB."
            return
        
        import base64
        from openai import OpenAIError
        
        client = get_vision_client()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Get readable language name for prompt
        language_name = LANGUAGE_MAP.get(chat_input.language, chat_input.language)
        
        vision_messages = [
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

LANGUAGE: Respond entirely in {language_name}. All explanations, troubleshooting steps, and guidance must be in {language_name}."""
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": clean_message or "What do you see in this image?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }
        ]
        
        try:
            response = await client.chat.completions.create(
                model=VISION_MODEL,
                messages=vision_messages,
                max_tokens=1000,
                stream=True
            )
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
            logger.log_interaction(user_id, clean_message, "VISION: Image analyzed", success=True)
            # Log Query (Vision success = not fallback)
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
    
    

    
    # ---------------------------------------------------------
    # IMPROVED: Contextualize Query (Chat History Awareness)
    # ---------------------------------------------------------
    search_query = clean_message
    if len(chat_input.conversation_history) > 0 and not image_bytes:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import StrOutputParser

            # Fast/Cheap model for rewriting
            history_llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=CONTEXT_MODEL, temperature=0)
            
            history_str = "\n".join([f"{msg.role}: {msg.content}" for msg in chat_input.conversation_history[-MAX_HISTORY_MESSAGES:]])
            
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
            search_query = await query_rewriter.ainvoke({"history": history_str, "question": clean_message})
            logger.log_interaction(user_id, clean_message, f"CONTEXT: Rewrote query to '{search_query}'", success=True)
            
        except Exception as e:
            logger.error(f"Query contextualization error: {e}", exc_info=True)
            search_query = clean_message # Fallback

    embedding_tokens = 0
    try:
        # 3. Retrieve Context (k=3 optimized for speed vs quality balance)
        # Use the REWRITTEN query for search, but keep original for other things if needed
        kb_results = await get_kb().search(search_query, k=3)
        # Accurate embedding token count
        embedding_tokens = len(_encoder.encode(clean_message))
        
        # Quality filtering: Remove low-relevance results
        filtered_results = [
            doc for doc in kb_results 
            if doc.metadata.get('score', 0) >= MIN_RELEVANCE_SCORE
        ]
        
        # If all results were filtered out, use best result anyway (fail-open)
        if not filtered_results and kb_results:
            logger.log_interaction(user_id, clean_message, 
                f"All results below threshold ({MIN_RELEVANCE_SCORE}), using best match", 
                success=True)
            filtered_results = kb_results[:1]  # Use top result
        
        # Format context with metadata and relevance scores
        context_parts = []
        for i, doc in enumerate(filtered_results, 1):
            source = doc.metadata.get('source', 'Unknown')
            page = doc.metadata.get('page', 0) + 1 # 0-indexed
            score = doc.metadata.get('score', 0)
            
            # Clean up source path to be just filename
            if "/" in source:
                source = source.split("/")[-1]
            if "\\" in source:
                source = source.split("\\")[-1]
            
            # Include relevance score and article number for AI reference
            context_parts.append(
                f"=== DOCUMENT {i} ===\n"
                f"METADATA: {{'source': '{source}', 'page': {page}, 'relevance': {score:.2f}}}\n"
                f"CONTENT:\n{doc.page_content}"
            )
            
        context = "\n\n---\n\n".join(context_parts)
        
        # Analytics logging preparation
        is_initial = len(chat_input.conversation_history) == 0
        is_fallback = len(filtered_results) == 0  # Fallback if no results passed threshold




        
        # 4. Generate Response (Real LLM)
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        if settings.OPENAI_API_KEY == "changeme":
            yield f"Simulated Response (Set API Key for real AI): I found {len(kb_results)} articles. Context: {context[:100]}..."
        else:
            llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=CHAT_MODEL, streaming=True)
            
            # Get readable language name for prompt
            language_name = LANGUAGE_MAP.get(chat_input.language, chat_input.language)
            
            # CONDITIONAL SYSTEM PROMPT: Deal Mode vs Chat Mode
            if is_deal_mode:
                system_content = f"""You are JUNA Deal Assistant, a sales enablement AI for Payroc payment processing reps.

YOUR MISSION:
Help reps build battle cards they trust enough to use with merchants—fast, complete, and confident.

CRITICAL RULES (NON-NEGOTIABLE):

1. DISCOVERY FLOW (v2.1 - All Questions at Once):
   - The user will provide initial context (vertical, state, provider, volume). This is NOT a question - it's background.
   - When user says "Generate all 3 guided questions" or "Start guided questions", return ALL 3 questions immediately.
   - Return questions in a structured JSON format with a "questions" array.
   - Do NOT ask questions one-at-a-time. Return all 3 upfront in a single response.
   
   Example flow:
   1. User: "Generate all 3 guided questions. Context: {{vertical: restaurant, volume: $75k}}"
   2. You: Return JSON with all 3 questions immediately (see format below)
   3. User will answer all 3 questions together
   4. User: "Generate battle card" with all answers provided
   
2. QUESTIONS TO RETURN (all 3 at once):
   When asked to generate questions, return this EXACT JSON structure:
   
   {{
     "questions": [
       "What's the biggest challenge they're facing with their current payment processor?",
       "What's their monthly transaction volume? (rough estimate is fine)",
       "What's their top priority: lower fees, better reporting, or faster transactions?"
     ]
   }}
   
   CRITICAL: Your response must be ONLY this JSON object. No text before or after. Start with {{ and end with }}.
   

3. BATTLE CARD OUTPUT (JSON ONLY):
   When user says "Generate battle card" or you've gathered enough info, respond with ONLY this JSON structure.
   
   CRITICAL FORMATTING RULES:
   - Your ENTIRE response must be valid JSON. No text before or after the JSON.
   - Start your response with {{ and end with }}
   - Do NOT write "Here's your battle card:" or any other explanation text
   - Do NOT use markdown formatting like **bold** inside the JSON
   - Just return the raw JSON object, nothing else
   
   EXACT STRUCTURE TO RETURN:
   
   {{
     "scenario": "One clear paragraph summarizing merchant's situation, volume, and needs.",
     "recommended_stack": [
       "Clover POS with KDS integration",
       "Advanced reporting package",
       "Mobile payment module"
     ],
     "why_this_wins": [
       {{"title": "Lower Fees", "detail": "Interchange+ pricing at 2.1% vs current 2.9% flat rate saves ~$600/month"}},
       {{"title": "Real-Time Reporting", "detail": "Sales by server, shift, and menu item—no more end-of-day surprises"}},
       {{"title": "Local Support", "detail": "On-site tech visits vs phone-only support"}}
     ],
     "pricing_framework": "Interchange-plus model, estimated 2.1% + $0.10 per transaction. Example: $75k monthly volume = ~$1,600/month processing costs.",
     "objections": [
       {{"objection": "We're locked into our current contract", "response": "Most restaurant contracts are month-to-month after the initial term. We can review yours and plan the switch timing."}},
       {{"objection": "Switching sounds complicated", "response": "We handle the full migration—menu programming, staff training, and parallel testing. You stay open throughout."}},
       {{"objection": "Your fees might be higher", "response": "Let's run a side-by-side comparison with your last 3 months of statements. Interchange+ typically saves 20-30% vs flat-rate."}}
     ],
     "next_steps": [
       "Schedule 30-min demo of reporting dashboard",
       "Send personalized pricing quote (3 business days)",
       "Review current contract for switch timing"
     ],
     "disclaimer": "This battle card is for internal sales use only. Do not share with merchants. All pricing subject to underwriting and final approval."
   }}
   
   REMEMBER: Return ONLY the JSON object. Your response must start with {{ and end with }}. No other text.

4. VOICE & TRUST RULES:
   - Use language reps would actually say to merchants
   - Be specific with numbers when you have data (volumes, savings, timelines)
   - Use ranges for pricing ("estimated 2.1-2.3%"), never exact quotes
   - No AI-isms: Never say "As an AI..." or "I don't have access to..."
   - Be confident but honest: "Based on $75k volume..." not "It might possibly..."
   
5. COMPLETENESS REQUIREMENTS:
   - Every section must have real content (no placeholders like "-" or "TBD")
   - "Why This Wins" must have 3-5 items with titles AND details
   - Objections must include both the objection and the response
   - Pricing must include methodology and real examples
   - If you don't have enough info for a section, ASK before generating

6. WHAT TO NEVER HALLUCINATE:
   - Specific product names (unless common: Clover, Square, Toast)
   - Exact pricing
   - Contract terms
   - Merchant eligibility

LANGUAGE: Respond entirely in {language_name}.

FOLLOW-UP SUGGESTIONS:
End every response with 2-3 clickable suggestions using this EXACT format:
<<SUGGESTIONS>>Topic 1|Topic 2|Topic 3

REMEMBER: Reps must trust every word enough to use it with a merchant. If you wouldn't say it on a sales call, don't write it."""
            else:
                # EXISTING CHATBOT SYSTEM PROMPT
                system_content = f"""You are JUNA, the AI support agent for onePOS (a Payroc company). You combine technical accuracy, service-minded communication, and calm problem-solving. Merchants rely on you to keep their restaurant running — you respect their time and treat every issue like it matters.

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
• Bold actions
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
            # Note: PII masking is hard on stream, we log the raw output for now or mask post-facto
            logger.log_interaction(user_id, clean_message, full_response, success=True)
            
            # 6. Log Query with token estimates for spend tracking
            # Accurate token counting with tiktoken
            message_text = " ".join([m.content for m in messages if hasattr(m, 'content') and m.content])
            input_tokens = len(_encoder.encode(message_text))
            output_tokens = len(_encoder.encode(full_response))
            get_analytics().log_query(
                chat_input.user_message, 
                is_initial, 
                is_fallback,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                embedding_tokens=embedding_tokens
            )
        
    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        logger.log_interaction(user_id, clean_message, "", success=False, error=str(e))
        yield "I encountered an error processing your request. Please try again."

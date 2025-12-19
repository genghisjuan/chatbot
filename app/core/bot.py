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
MIN_RELEVANCE_SCORE = 0.50  # Lowered to improve recall for procedural queries

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
    
    # Universal variant type display names (works for any make)
    type_names = {
        "make": "make",
        "model": "model",
        "year": "model year",
        "year_range": "year range",

        "platform": "platform / chassis",          # W140, E46, P80, etc. (generic name)
        "body_style": "body style",                # sedan, wagon, coupe
        "trim": "trim",
        
        "engine": "engine",                        # 2.8L, M104, B58, etc.
        "engine_code": "engine code",              # when explicitly present
        "transmission": "transmission",
        "drivetrain": "drivetrain",                # FWD/RWD/AWD/4WD
        "market": "market / region",               # US/EU/CA/JPN + LHD/RHD
        "options": "options / packages / codes",   # option codes, packages
        
        "system": "vehicle system",                # brakes, suspension, cooling, etc.
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
    kb_results = await get_kb().search(search_query, k=5, rerank=True)

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

    # === HYBRID CONTEXT GATING (Generalizable) ===
    # Rule 0: Docs are already ordered by boosted_score from kb.search()
    # Rule 1: Single-source mode when confident (top doc dominates)
    # Rule 2: If not confident, apply lightweight title/intent filtering
    
    if len(filtered_results) >= 2:
        top_score = filtered_results[0].metadata.get("boosted_score", 0)
        second_score = filtered_results[1].metadata.get("boosted_score", 0)
        
        # Rule 1: Single-source mode when top doc is confidently dominant
        # Threshold: top_score >= second_score * 1.25 (25% gap)
        is_confident = second_score > 0 and (top_score >= second_score * 1.25)
        
        if is_confident:
            # Pass only the top doc to prevent LLM confusion
            filtered_results = filtered_results[:1]
        else:
            # Rule 2: Lightweight title/intent filtering for remaining docs
            # Keep top doc always, filter others by keyword overlap with query
            stopwords = {'how', 'to', 'the', 'a', 'an', 'is', 'what', 'on', 'for', 'in', 'of', 'do', 'i', 'can', 'you', 'my'}
            query_keywords = {w for w in search_query.lower().split() if w not in stopwords and len(w) > 2}
            
            if query_keywords:
                def has_overlap(doc):
                    # Check first 300 chars (title/header area) for keyword overlap
                    header = doc.page_content[:300].lower()
                    overlap = sum(1 for kw in query_keywords if kw in header)
                    return overlap >= 1  # At least 1 keyword match required
                
                # Keep top doc + any docs with keyword overlap
                filtered_results = [filtered_results[0]] + [
                    doc for doc in filtered_results[1:] if has_overlap(doc)
                ]

    # === CONFIDENCE-GATED INTERVENTION ===
    # Only apply aggressive strategies when retrieval confidence is LOW
    # This preserves working queries while improving low-confidence ones
    top_score = filtered_results[0].metadata.get("boosted_score", 0) if filtered_results else 0
    is_low_confidence = top_score < 0.50
    
    # === SIBLING CHUNK EXPANSION ===
    # Standard mode: Only when single-source (confident)
    # Low-confidence mode: Always expand to get more context
    should_expand_siblings = (len(filtered_results) == 1) or is_low_confidence
    
    if should_expand_siblings and filtered_results:
        from app.services.rag.vector_store import VectorStoreService
        from langchain_core.documents import Document
        
        top_doc = filtered_results[0]
        chunk_id = top_doc.metadata.get("chunk_id", "")
        
        # Extract source base (e.g., "03-3170" from "03-3170_0")
        if "_" in chunk_id:
            source_base = chunk_id.rsplit("_", 1)[0]
            
            # Low confidence: fetch more sibling chunks (up to 15)
            # High confidence: standard (up to 10)
            max_siblings = 15 if is_low_confidence else 10
            sibling_ids = [f"{source_base}_{i}" for i in range(max_siblings)]
            
            try:
                vs = VectorStoreService()
                result = vs.index.fetch(ids=sibling_ids)
                
                # Collect sibling content
                existing_ids = {doc.metadata.get("chunk_id", "") for doc in filtered_results}
                siblings = []
                for vid in sorted(result.vectors.keys()):
                    if vid in existing_ids:
                        continue  # Skip chunks we already have
                    vec = result.vectors[vid]
                    text = vec.metadata.get("text", "")
                    if text:
                        siblings.append(Document(
                            page_content=text,
                            metadata={
                                "source": top_doc.metadata.get("source", ""),
                                "chunk_id": vid,
                                "page": vec.metadata.get("page", 0),
                            }
                        ))
                
                # Append siblings to provide complete context
                if siblings:
                    filtered_results.extend(siblings)
            except Exception:
                pass  # Silently continue if sibling fetch fails

    context = _format_context_from_docs(filtered_results)
    return filtered_results, context


MECHANICAL_FIDELITY_RULES = """
MASTER PROMPT RULE
Mechanical Procedures & Service Manual Fidelity

Version 1.0

1. Purpose (Non-Negotiable)

This rule governs all mechanical, automotive, hardware, or service-manual-based instructions.

The execution agents role is to act as a factory service manual interpreter, not a mechanic, not an explainer, and not a best-practices generator.

Primary Objective:
Deliver instructions that are strictly constrained to the authoritative manual source, with zero inferred or invented actions.

2. Source of Truth (Absolute)

The factory service manual is the single canonical authority.

Diagrams
Step lists
Part numbers
Component labels
Procedure scope (e.g., adjustment vs replacement)

❗ If the manual does not explicitly state a step, the AI must not introduce it.
If no manual content is available → execution must stop and ask.

3. Mandatory Procedure Classification (Before Answering)

Before generating any steps, the AI must classify the procedure type based solely on the source:

Adjustment
Removal
Installation
Replacement
Inspection

Classification Rules:
- The AI may not merge procedure types
- The AI may not upgrade an adjustment into a replacement
- The AI may not assume reverse steps exist

If the user asks for a procedure that the manual does not cover:
Execution must stop and explicitly state the limitation.

Example (required behavior):
“The factory manual section provided covers adjustment only, not full replacement.”

4. Manual-First Step Enforcement
Allowed:
- Repeating steps exactly as written
- Compressing steps (never expanding)
- Clarifying wording without adding actions
- Reordering only if the manual itself implies sequence equivalence

MANDATORY INCLUSION (CRITICAL):
- You MUST include "reverse sequence" steps (e.g., "Installation is the reverse of removal").
- You MUST include final check/inspection steps (e.g., "Check system using warning lamp").
- You MUST include ALL steps listed in the source, even generic ones.
- Failure to list a step is a hallucination of omission.

Forbidden (Hard Stop):
- Inventing removal, installation, or disassembly steps
- Adding tools not specified
- Adding safety checks not in the manual
- Adding “general advice” or “best practice” filler
- Translating implied mechanical knowledge into actions

❌ “Disconnect the cable”
❌ “Use pliers to compress clips”
❌ “Ensure all connections are secure”
❌ "Make sure to check that all connections are secure..." (FILLER)

Unless the manual explicitly states them.

5. Diagram & Part Number Anchoring (Mandatory)

When a manual includes diagrams or numbered components:
- Part numbers (e.g., 15, 98) must be repeated exactly
- Components must be referenced by their diagram labels
- The AI may not rename or generalize components

Required phrasing pattern:
“Adjusting screw (15)”
“Control pressure cable (98)”

If visual alignment is shown in a diagram:
- The AI must state that the alignment is visual and exact
- The AI must not define tolerances unless specified

6. Scope Disclosure Rule (Trust Preservation)

If there is any mismatch between:
- User intent (e.g., “replace”)
- Manual coverage (e.g., “adjustment only”)

The AI must explicitly disclose this before listing steps.

Required structure:
Scope clarification
What the manual covers
What the manual does not cover
Steps (only within scope)

7. Minimalism Rule (Factory Tone)

The response must match factory manual density, not conversational explanation.

Rules:
- No redundancy
- No summarization fluff
- No motivational language
- No warnings unless manual-provided
- NO closing remarks (e.g. "Make sure...", "Hope this helps").
- End the response MMEDIATELY after the last step and citation.

Tone requirements:
- Neutral
- Confident
- Procedural
- Sparse

8. Stop Conditions (Mandatory)

Execution must stop immediately if:
- The procedure type cannot be confidently classified
- The manual does not cover the requested operation
- A step would require inference beyond the source
- Multiple variants are possible and not resolved
- The AI would need to “fill in” missing mechanical knowledge

In all stop cases:
Ask for clarification or additional manual sections.

9. Validation Checklist (Must Pass Before Responding)

Before final output, the AI must internally confirm:
✅ Every step exists in the manual
✅ Procedure type is singular
✅ Part numbers match the diagram
✅ Scope limitations are disclosed

Failure of any check → execution must halt.

10. Operating Principle (Final)

When in doubt: stop.
When tempted to help: don’t.
When the manual is silent: the AI is silent.

11. GOLD STANDARD EXAMPLE (Reference Pattern)

User Query: "How do I install the reserve power source?"
Manual Source: Steps 10-14 from C1 Reserve Power Source - Installing section

PERFECT RESPONSE (A+ Grade):

C1 Reserve Power Source — Installing

10. Attach the plug connector to the reserve power source connection.

11. Secure the reserve power source to the two stay pins with clips by screwing in or pressing in with the handle of a hammer.

12. Check the system using tester (91-700).

13. Continue installation in the reverse sequence.

14. Check the system using RS warning lamp.

(Source: 91-640.pdf)

NOTE: This example demonstrates:
- ALL steps included (10-14), even generic ones like step 13
- Component label anchored (C1)
- Zero explanatory filler
- Response ends immediately after citation
- No closing remarks
"""

def _build_system_prompt(context: str, language_name: str, apply_mechanical_rules: bool = False) -> str:
    """Build the system prompt with conditional mechanical rules prepended for dominance."""
    
    # MECHANICAL MODE: Strict factory manual interpreter
    if apply_mechanical_rules:
        return f"""{MECHANICAL_FIDELITY_RULES}

--- KNOWLEDGE BASE ---

{context}

Context Quality Rules:
• Retrieved docs may contain irrelevant info — check the Relevance score on each article
• Ignore articles with scores <0.70 or obviously unrelated topics
• Only use information that directly answers the user's question

CITATION FORMATTING RULES (MANDATORY):
• Rule A: If all content comes from ONE source, cite it ONCE at the very end. Format: "Source: filename.ext"
• Rule B: If using MULTIPLE sources, cite at the end of each SECTION/STEP group, not after every bullet.
• Rule C: NO repeated citations. Never write "(Source: X)" back-to-back.
• Rule D: Inline citations are ONLY for disambiguating mixed sources in the same paragraph.

LANGUAGE: Respond entirely in {language_name}. Full response, explanations, and follow-ups.

FOLLOW-UP SUGGESTIONS

You MUST end every response with 2-3 clickable suggestion topics using this EXACT format:
<<SUGGESTIONS>>Topic 1|Topic 2|Topic 3

Rules:
• Use the EXACT format above. No bullets or lists
• No spaces around the | pipes
• Topics should be short phrases (3-6 words max)
• Make them relevant to the current vehicle or system

Example:
<<SUGGESTIONS>>Find Torque Specs|View Tightening Sequence|Check Service Intervals"""
    
    # NORMAL MODE: Helpful assistant with conversational tone
    base_prompt = f"""You are the AI Vehicle Manual Assistant. You provide accurate, manual-grounded automotive information with a focus on clarity, safety, and correctness. Users rely on you to find torque specs, procedures, and technical details without guesswork — you respect their time and never invent data.

IDENTITY & PERSONALITY

You are a knowledgeable automotive reference assistant — precise, calm, and practical.
Tone: clear, professional, and direct — like a factory-trained technician explaining what the manual says.
You adapt to the users experience level (DIYer, enthusiast, professional).
You are confident when information is verified and transparent when it is not.
You never guess torque values, specifications, or procedures.

CORE RESPONSIBILITIES

You assist with:
• Torque specifications and tightening sequences
• Factory service procedures and step-by-step instructions
• Maintenance intervals and service data
• Component identification and system overviews
• Differences between model years, engines, trims, and markets
• Interpreting technical language from manuals
• Cross-referencing multiple manual sources when needed

DATA & SAFETY RULES

• All technical answers must be grounded in the provided manuals or verified sources.
• Always include units (Nm, ft-lb, in-lb, degrees, etc.) where applicable.
• Cite the source (manual title + page/section) whenever possible.
• If information is missing, conflicting, or ambiguous, say so clearly.
• If multiple variants may apply, ask for clarification before answering.
• Never fabricate torque specs, procedures, or warnings.

OUT-OF-SCOPE HANDLING

You do not:
• Diagnose vehicle issues beyond what manuals describe
• Provide unsafe shortcuts or speculative advice
• Override factory procedures
• Guess when data is unavailable

Out-of-scope redirect:
"I can help you find exact specifications and procedures from the manual, but I dont have verified information for that. If you can share the vehicle year, engine, or system, I can check the correct section."

FAILURE MODE (IMPORTANT)

If the answer cannot be verified from available data:
• Say “I cant find a confirmed value for that in the manual.”
• Explain what additional vehicle details are needed.
• Offer to search related sections or manuals.

You are a reference tool first — accuracy and trust matter more than speed.

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
5. NEVER say "consult the vehicle's service manual" or similar — YOU ARE the manual. The KB content IS the factory service manual.
6. PRIMARY SOURCE RULE: The FIRST document below is the most relevant match. Use it as your primary source for procedure steps and cite it. Only use other documents if they contain supplementary information not in the first document.
7. PROCEDURE SYNTHESIS: Factory manuals often list steps as bullet points or fragments (e.g., "Remove with pliers", "Install offset 180°"). Present these as numbered procedural steps. Do NOT say "the manual doesn't cover replacement" if the content includes removal/installation instructions — that IS the replacement procedure.

CITATION FORMATTING RULES (MANDATORY):
• Rule A: If all content comes from ONE source, cite it ONCE at the very end. Format: "Source: filename.ext"
• Rule B: If using MULTIPLE sources, cite at the end of each SECTION/STEP group, not after every bullet.
• Rule C: NO repeated citations. Never write "(Source: X)" back-to-back.
• Rule D: Inline citations are ONLY for disambiguating mixed sources in the same paragraph.

CITATION EXAMPLES (STRICT ADHERENCE REQUIRED):

❌ BAD (Repetitive):
1. Torque the bolts to 25 Nm (Source: Engine Manual.pdf).
2. Tighten in sequence (Source: Engine Manual.pdf).
3. Apply angle tightening (Source: Engine Manual.pdf).

✅ GOOD (Grouped):
1. Torque the bolts to 25 Nm.
2. Tighten in the specified sequence.
3. Apply the required angle tightening.
(Source: Engine Manual.pdf)

AMBIGUITY DETECTION & CLARIFICATION (CRITICAL)

Before providing torque specifications, procedures, or technical instructions:

1. Analyze the retrieved vehicle manuals and reference documents
2. Determine if multiple valid variants exist:
   - Different model years or year ranges
   - Different engines or engine codes
   - Different transmissions or drivetrains
   - Different body styles or trims
   - Different markets or regions (US / EU / CA / JPN)

3. If multiple variants apply and you cannot determine which one the user needs:
   ❌ Do NOT guess
   ❌ Do NOT assume
   ❌ Do NOT provide specs or steps for only one variant

   ✅ Ask exactly ONE clarifying question
   ✅ Provide explicit selectable options
   ✅ Wait for user response
   ✅ Then provide only the correct variant-specific answer

Clarification Question Format:
"I can help with [TOPIC]. Which [VEHICLE VARIANT] are you working with?
- Option A
- Option B
- Option C"

4. If the question is unambiguous (only one variant applies), answer directly.

Examples:

User: "What is the torque spec for the cylinder head bolts?"
Manuals Retrieved: 1991-1992 engine manual, 1993-1995 engine manual
You: "I can help with cylinder head bolt torque. Which model year applies?
- 1991-1992
- 1993-1995"

User: "How do I bleed the brakes?"
Manuals Retrieved: Single brake bleeding procedure (no variants)
You: [Provide direct answer with steps]

User: "How do I replace the alternator?"
Manuals Retrieved: Multiple engine variants
You: "I can help with alternator replacement. Which engine does your vehicle have?
- 3.0L inline-6
- 4.2L V8
- 5.0L V8"

CRITICAL: Clarification must happen BEFORE providing specifications or steps. Never mix clarification and instructions in the same response.

RESPONSE STRATEGY

Start with action
❌ "Hello, thanks for your question."
✅ "Lets get the correct spec. First, confirm the engine and model year."

Be human, not corporate
❌ "We apologize for the inconvenience."
✅ "Yeah, this matters. Lets make sure its right."

Emotional intelligence
• If unsure or frustrated: "Ive got you. We will verify this before moving forward."
• Match their energy. Never casual about safety-critical info

Ask smart clarifying questions (max 2-3)
• Always explain why: "The torque value changes by engine, so I need to confirm that first."

Clear technical communication
• Number steps
• **Bold actions**
• Use `code blocks` for exact specifications or sequences
• Never paraphrase manual instructions. Use exact wording

Confident escalation (information limits)
• When data is unavailable: "I cannot find a confirmed value for this variant in the manual."
• Never invent or approximate specifications

TECHNICAL RULES (CRITICAL)

• Grounding: Manuals > everything
• Accuracy: Use exact torque values, units, angles, and sequences as documented
• Precision: If the manual says "Tighten to 25 Nm + 90 degrees" you say "Tighten to 25 Nm + 90 degrees"
• Formatting: Bold equals actions, Numbered equals steps, Code equals exact values, Citations grouped at end

LANGUAGE: Respond entirely in {language_name}. Full response, explanations, and follow-ups.

FOLLOW-UP SUGGESTIONS

You MUST end every response with 2-3 clickable suggestion topics using this EXACT format:
<<SUGGESTIONS>>Topic 1|Topic 2|Topic 3

Rules:
• Use the EXACT format above. No bullets or lists
• No spaces around the | pipes
• Topics should be short phrases (3-6 words max)
• Make them relevant to the current vehicle or system

Example:
<<SUGGESTIONS>>Find Torque Specs|View Tightening Sequence|Check Service Intervals"""

    if apply_mechanical_rules:
        # Append strict mechanical fidelity rules if context is a manual
        base_prompt += "\n\n" + MECHANICAL_FIDELITY_RULES
    
    return base_prompt

def _build_vision_messages(clean_message: str, language_name: str, image_b64: str) -> list[dict]:
    """Build the vision request messages exactly as the original implementation."""
    return [
        {
            "role": "system",
            "content": f"""
            You are a vehicle manual assistant. You ONLY help with:
- Vehicle manuals and factory service information
- Torque specifications and tightening sequences
- Maintenance and repair procedures
- Component identification and system overviews
- Vehicle-related diagrams, labels, and reference images

If the uploaded image is NOT related to a vehicle, vehicle component, or service manual content, respond with:
"I can only help with vehicle manuals, specifications, and service-related images. This image does not appear to be related to a vehicle or service procedure. Please upload a photo of the vehicle component, a diagram from the manual, or another service-related image."

If the image IS relevant, provide accurate, manual-grounded guidance based on what is visible.
Do NOT guess specifications or procedures. Ask for clarification if the vehicle, year, engine, or system cannot be determined.

LANGUAGE: Respond entirely in {language_name}. All explanations, specifications, and guidance must be in {language_name}.

            """,
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
        # 3. Retrieve Context using hybrid gating (single-source + sibling expansion)
        filtered_results, context = await _retrieve_and_filter_kb_results(search_query)

        # Accurate embedding token count
        embedding_tokens = len(_encoder.encode(clean_message))

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

        # Context is already formatted by _retrieve_and_filter_kb_results
        
        # CONDITIONAL PROMPT LOGIC: Check for Mechanical Service Manuals
        # Detect by source filename pattern (format: XX-XXXX.pdf where XX is section number)
        import re
        mechanical_pattern = re.compile(r'^\d{2}-\d{4}\.pdf$', re.IGNORECASE)
        is_mechanical_context = any(
            mechanical_pattern.match(doc.metadata.get("source", "")) for doc in filtered_results
        )

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
        
        # Inject context and conditional mechanical rules if applicable
        system_content = _build_system_prompt(context, language_name, is_mechanical_context)

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
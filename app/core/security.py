import re
import unicodedata
from typing import Optional

def normalize_unicode(text: str) -> str:
    """Normalize Unicode to prevent lookalike character bypasses."""
    return unicodedata.normalize('NFKC', text)

def sanitize_input(text: Optional[str]) -> str:
    """
    Remove control characters and excessive whitespace.
    Preserves emoji and international characters.
    
    Args:
        text: Input text to sanitize (can be None)
        
    Returns:
        Sanitized text (empty string if input was None)
        
    Raises:
        TypeError: If input is not str or None
    """
    if text is None:
        return ""
    
    if not isinstance(text, str):
        raise TypeError(f"Expected str or None, got {type(text).__name__}")
    
    # Only remove control characters (category Cc), keep emoji/unicode
    cleaned = "".join(
        ch for ch in text 
        if unicodedata.category(ch) != 'Cc' or ch in "\n\t"
    )
    
    return cleaned.strip()

def detect_injection(text: str, user_id: Optional[str] = None) -> bool:
    """
    Detect prompt injection attempts using pattern matching.
    
    This uses keyword-based detection with Unicode normalization.
    In production, consider augmenting with LLM-based classification.
    
    Args:
        text: User input to check
        user_id: Optional user ID for logging
        
    Returns:
        True if injection detected, False otherwise
    """
    # Validate input
    if not text:
        return False  # Empty text cannot be an injection
    
    injection_patterns = [
        # Instruction manipulation
        r"ignore\s+(all\s+)?(previous|prior|earlier|above)\s+(instructions?|rules?|commands?|prompts?)",
        r"(forget|disregard|override)\s+(what|everything|all)",
        
        # Role manipulation
        r"(you\s+are|act\s+as|pretend\s+to\s+be|roleplay\s+as)\s+(now\s+)?(a|an|the)?\s*\w+",
        r"(dan|jailbreak|sudo\s+mode|developer\s+mode|admin\s+mode)",
        
        # System probing
        r"(reveal|show|tell\s+me|what\s+are)\s+(your|the)\s+(rules?|instructions?|system\s+prompt)",
        r"repeat\s+(your|the)\s+(instructions?|prompt|rules?)",
        
        # Encoding tricks
        r"(base64|rot13|hex|unicode)\s*(encode|decode)?",
        
        # Boundary attacks
        r"(ignore|skip)\s+everything\s+(after|before)",
        r"\[SYSTEM\]|\[\/INST\]|<\|.*?\|>",  # LLM instruction delimiters
        
        # Original patterns (kept for backwards compatibility)
        r"system\s+override",
        r"reveal\s+your\s+rules",
        r"ignore\s+all\s+rules",
    ]
    
    # Normalize Unicode to prevent lookalike character bypasses (e.g., Cyrillic 'і' vs Latin 'i')
    normalized_text = normalize_unicode(text.lower())
    
    for pattern in injection_patterns:
        if re.search(pattern, normalized_text):
            # Log security event
            try:
                from app.services import logger
                logger.log_security_event(
                    "PROMPT_INJECTION_DETECTED",
                    f"User {user_id or 'anonymous'}: Pattern matched in: {text[:100]}..."
                )
            except ImportError:
                # Logger not available during import or testing
                pass
            return True
    
    return False

def mask_pii_for_logging(text: str) -> str:
    """
    Mask PII (emails, phone numbers) for logging and analytics ONLY.
    
    WARNING: DO NOT use this on user-facing content or user input!
    Only use when logging to files/databases to protect user privacy.
    
    For a payment chatbot, users legitimately need to reference emails
    like "support@payroc.com" or "send receipt to john@example.com".
    
    Args:
        text: Log text to mask
        
    Returns:
        Text with emails and phone numbers masked
    """
    if not text:
        return ""
    
    # Mask email addresses
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL]', text)
    
    # Mask phone numbers (more restrictive pattern to reduce false positives)
    # Matches: +1-555-123-4567, (555) 123-4567, 555.123.4567, 5551234567
    text = re.sub(r'\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]', text)
    
    return text

def mask_pii(text: str) -> str:
    """
    DEPRECATED: Use mask_pii_for_logging() instead.
    
    This function is kept for backwards compatibility but should not be used.
    Use mask_pii_for_logging() to make it clear this is for logging only.
    """
    return mask_pii_for_logging(text)


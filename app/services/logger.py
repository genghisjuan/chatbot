import logging
import json
from typing import Optional

# Configure logging
# Note: basicConfig should be called in main.py, not here, to avoid overriding app defaults.
logger = logging.getLogger(__name__)

def log_interaction(user_id: str, input_text: str, output_text: str, success: bool, error: Optional[str] = None):
    """
    Log interaction metadata. Avoid logging raw PII if possible.
    """
    log_entry = {
        # "timestamp" handled by log formatter
        "user_id": user_id,
        "input_length": len(input_text),
        "output_length": len(output_text),
        "success": success,
        "error": str(error) if error else None
    }
    # Use default=str to safely serialize any non-standard types
    logger.info(json.dumps(log_entry, default=str))

def log_security_event(event_type: str, details: str):
    """
    Log security-related events.
    """
    log_entry = {
        # "timestamp" handled by log formatter
        "event_type": event_type,
        "details": details,
        "level": "SECURITY"
    }
    logger.warning(json.dumps(log_entry, default=str))

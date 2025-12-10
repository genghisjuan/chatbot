# Logger Service Documentation

## Overview
The **Logger Service** (`logger.py`) provides a centralized, standard logging interface for the support chatbot application. It wraps Python's standard `logging` library to ensure consistent formatting for interaction logs and security events.

## Architecture
- **Standard Library**: Uses Python's built-in `logging` module.
- **Structured Logging**: Serializes log payloads to JSON strings to support log aggregation systems (e.g., Datadog, ELK stack).
- **Safety**: Automatically converts non-serializable objects (like Exceptions) to strings to prevent logging crashes.

## API Reference

### `log_interaction(user_id, input_text, output_text, success, error=None)`
Logs a user interaction event.
- **Level**: `INFO`
- **Payload**:
  - `user_id`: ID of the user.
  - `input_length`: Length of user input.
  - `output_length`: Length of bot response.
  - `success`: Boolean status.
  - `error`: Error message or exception string (optional).

### `log_security_event(event_type, details)`
Logs a security-relevant event.
- **Level**: `WARNING`
- **Payload**:
  - `event_type`: Category of event (e.g., "UNAUTHORIZED_ACCESS").
  - `details`: Contextual information.
  - `level`: "SECURITY".

## Usage Example

```python
from app.services.logger import log_interaction, log_security_event

# Log a successful chat
log_interaction(
    user_id="user_123",
    input_text="Hello",
    output_text="Hi there!",
    success=True
)

# Log an error
try:
    1 / 0
except Exception as e:
    log_interaction(
        user_id="user_123",
        input_text="calc",
        output_text="",
        success=False,
        error=e  # Automatically converted to str(e)
    )
```

## Configuration
Logging configuration (level, format, handlers) should be set in the application entry point (e.g., `main.py`). This module intentionally does **not** call `logging.basicConfig()` to avoid overriding global settings.


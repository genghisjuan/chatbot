# Email Service Documentation

## Overview
The **Email Service** (`email_service.py`) manages support ticket notifications. It handles:
- Support Requests (General tickets)
- Callback Requests
- Inbound Call Alerts

It supports **SMTP** for real emails and a **Demo Mode** (flat file storage) when SMTP is not configured.

## Architecture
- **Ticket IDs**: Generates unique IDs using `Timestamp + Random Hex` format (e.g., `#20231209-1430-A1B2`) to be process-safe without needing a database.
- **Asynchronous**: Built on `aiosmtplib` and `asyncio` for non-blocking operation.
- **Demo Mode**: If SMTP settings are missing, emails are saved as `.txt` files in `data/email_service/emails/`.

## Configuration
The service is configured via `app.core.config.settings`:

| Setting | Description | Default |
|Or|---|---|
| `SUPPORT_EMAIL` | Destination for support tickets | `jhamilton831@gmail.com` |
| `SMTP_SERVER` | SMTP Hostname | None (Trigger Demo Mode) |
| `SMTP_PORT` | SMTP Port | None |
| `SMTP_USERNAME` | SMTP Auth User | None |
| `SMTP_PASSWORD` | SMTP Auth Password | None |
| `OPENAI_API_KEY` | For generating chat summaries | `changeme` |

## API Reference

### `EmailService` Class

#### `send_support_email(name, business, user_summary, history)`
Sends a standard support ticket.
- **Returns**: Ticket ID (str)
- **Demo Output**: `data/email_service/emails/ticket_#ID.txt`

#### `send_callback_request(phone, preferred_time, history)`
Request for a phone callback.
- **Returns**: Ticket ID (str)
- **Demo Output**: `data/email_service/emails/callback_#ID.txt`

#### `create_inbound_call_ticket(phone, history)`
Alert for an active inbound call.
- **Returns**: Ticket ID (str)
- **Demo Output**: `data/email_service/emails/call_#ID.txt`

### Internal Helpers
- `_get_next_ticket_id()`: Generates collision-resistant IDs.
- `_generate_chat_summary()`: Uses GPT-4o to summarize chat history.
- `_send_or_save()`: Unified logic for dispatching emails.

## Usage Example

```python
from app.services.email_service import EmailService

email_svc = EmailService()

# Send a ticket
ticket_id = await email_svc.send_support_email(
    name="John Doe",
    business="Acme Corp",
    user_summary="Printer on fire",
    history=chat_history_list
)
print(f"Ticket created: {ticket_id}")
```


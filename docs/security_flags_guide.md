# Test 3: Security Flags - Detailed Guide

## Overview
Test 3 verifies that the security hardening flags work correctly in production configuration.

## What Are These Flags?

### SANITIZE_ERRORS (Default: False)
**Purpose:** Prevents leaking internal exception details to API clients

**When OFF (default):**
```json
{
  "detail": "Internal server error: division by zero"
}
```
Shows the actual error - useful for debugging in development.

**When ON:**
```json
{
  "detail": "Internal server error"
}
```
Hides implementation details - prevents info leakage in production.

**Important:** Server logs ALWAYS contain full stack traces regardless of this flag.

---

### STRICT_HISTORY_VALIDATION (Default: False)
**Purpose:** Prevents Denial of Service (DoS) attacks via malicious conversation history payloads

**When OFF (default):**
- Basic JSON parsing only
- No message count limits
- No per-message size limits
- Backward compatible with existing clients

**When ON:**
- Maximum 100 messages in history
- Each message max 10,000 characters
- Strict type checking (must be array of objects)
- Required fields validation (role, content)

---

## How to Test

### Step 1: Verify Current State (Flags OFF)
```bash
# Check current flags (should both be False)
python -c "from app.core.config import settings; print(f'SANITIZE_ERRORS: {settings.SANITIZE_ERRORS}'); print(f'STRICT_HISTORY_VALIDATION: {settings.STRICT_HISTORY_VALIDATION}')"
```

Expected output:
```
SANITIZE_ERRORS: False
STRICT_HISTORY_VALIDATION: False
```

### Step 2: Test Error Sanitization

**2a. Baseline (Flag OFF)**
1. Visit http://localhost:8000
2. Open browser developer console (F12)
3. Send a chat message
4. If an internal error occurs, you'll see detailed error messages

**2b. Enable Flag**
Add to `.env`:
```
SANITIZE_ERRORS=true
```

Restart server:
```bash
Get-Process python | Stop-Process -Force; Start-Sleep -Seconds 2; python start.py
```

**2c. Verify Sanitization**
- Trigger an error (e.g., send malformed data)
- Error response should be generic: "Internal server error"
- Server console/logs should still show full details

---

### Step 3: Test Strict History Validation

**3a. Baseline (Flag OFF)**
Create test script `test_history.py`:
```python
import requests

# Test: Send 150 messages (should work with flag OFF)
history = [{"role": "user", "content": f"message {i}"} for i in range(150)]

response = requests.post(
    "http://localhost:8000/api/v1/chat",
    data={
        "user_message": "test",
        "conversation_history": str(history),
        "language": "en-US"
    },
    stream=True
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text[:100]}")
```

Expected: Success (200 OK)

**3b. Enable Flag**
Add to `.env`:
```
STRICT_HISTORY_VALIDATION=true
```

Restart server.

**3c. Verify Limits**
Re-run test script:
- Expected: 400 error "conversation_history exceeds maximum length (100 messages)"

**Valid test (50 messages):**
```python
history = [{"role": "user", "content": "test"}] * 50
# Should succeed
```

**Invalid tests:**
```python
# Too many messages
history = [{"role": "user", "content": "test"}] * 101
# Expected: 400 error

# Message too long
history = [{"role": "user", "content": "x" * 10001}]
# Expected: 400 error

# Missing required field
history = [{"role": "user"}]  # No content
# Expected: 400 error

# Wrong type
history = {"not": "array"}
# Expected: 400 error "must be a JSON array"
```

---

### Step 4: Test Both Flags Together

**.env:**
```
SANITIZE_ERRORS=true
STRICT_HISTORY_VALIDATION=true
```

Restart server.

**Test:**
1. Send valid request → Works normally
2. Send 101 messages → Rejected with sanitized error
3. Trigger internal error → Generic error message (details in logs only)

---

## Production Rollout Strategy

### Phase 1: Staging (Week 1)
```
SANITIZE_ERRORS=false
STRICT_HISTORY_VALIDATION=false
```
Verify baseline behavior identical to current production.

### Phase 2: Strict Validation (Week 2)
```
SANITIZE_ERRORS=false
STRICT_HISTORY_VALIDATION=true  ← Enable
```
- Monitor rejection rates
- Verify legitimate users unaffected (100 message limit is generous)
- Check logs for any unexpected rejections

### Phase 3: Error Sanitization (Week 3)
```
SANITIZE_ERRORS=true  ← Enable
STRICT_HISTORY_VALIDATION=true
```
- Monitor error rates
- Verify sensitive details not leaked
- Confirm debugging still possible via server logs

### Phase 4: Production (Week 4)
Deploy to production with both flags enabled.

---

## Quick Reference

| Flag | Default | When to Enable | Risk |
|------|---------|----------------|------|
| `SANITIZE_ERRORS` | `False` | Production only | Low - only affects error messages |
| `STRICT_HISTORY_VALIDATION` | `False` | After testing limits | Low - 100 msg limit is generous |

## Troubleshooting

**"My requests are being rejected"**
- Check if you're sending >100 messages
- Check if any message >10K characters
- Verify conversation_history is a JSON array
- Ensure all messages have `role` and `content`

**"I can't see error details"**
- Check server logs (always have full details)
- Set `SANITIZE_ERRORS=false` in development
- Use `python start.py` to see console output

**"How do I know what's in my logs?"**
View `logs/server.log` - full stack traces are always there regardless of flags.

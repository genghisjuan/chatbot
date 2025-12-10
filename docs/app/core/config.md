# Configuration Documentation

## Overview

**File**: [`app/core/config.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/core/config.py)

The Configuration module manages all application settings using Pydantic BaseSettings with automatic environment variable loading. This module provides type-safe, validated configuration with clear error messages for missing or invalid settings.

---

## Table of Contents

1. [Summary](#summary)
2. [Settings Class](#settings-class)
3. [Configuration Fields](#configuration-fields)
4. [Field Validators](#field-validators)
5. [Setup Instructions](#setup-instructions)
6. [Usage](#usage)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Summary

**Key Features**:
- ✅ **Type-safe configuration** with Pydantic validation
- ✅ **Automatic .env loading** via python-dotenv
- ✅ **Required field validation** with helpful error messages
- ✅ **Singleton pattern** for consistent settings across app
- ✅ **Security-first** design (no hardcoded secrets)

**Settings Loaded**:
- OpenAI API credentials (REQUIRED)
- Pinecone vector database credentials (REQUIRED)
- Database connection string
- AWS S3 configuration (optional)
- SMTP email settings (optional)

---

## Settings Class

### Class Definition

```python
class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
```

**Base Class**: `pydantic_settings.BaseSettings`

**Configuration**:
```python
model_config = SettingsConfigDict(
    env_file=".env",           # Loads from .env file
    env_file_encoding="utf-8",  # UTF-8 encoding
    case_sensitive=True         # Env vars must be UPPERCASE
)
```

---

## Configuration Fields

### Required Settings

#### OPENAI_API_KEY
```python
OPENAI_API_KEY: str = Field(
    default="",
    description="OpenAI API key for embeddings and LLM (REQUIRED)"
)
```

**Type**: `str`  
**Required**: Yes  
**Format**: Must start with `"sk-"`  
**Get Key**: https://platform.openai.com/api-keys

**Validation**:
- Strips whitespace
- Checks if empty
- Validates format (starts with "sk-")

**Example**:
```bash
OPENAI_API_KEY=sk-proj-abc123...
```

---

#### PINECONE_API_KEY
```python
PINECONE_API_KEY: str = Field(
    default="",
    description="Pinecone API key for vector search (REQUIRED)"
)
```

**Type**: `str`  
**Required**: Yes  
**Get Key**: https://www.pinecone.io/

**Validation**:
- Strips whitespace
- Checks if empty

**Example**:
```bash
PINECONE_API_KEY=your-pinecone-key-here
```

---

### Database Settings

#### DATABASE_URL
```python
DATABASE_URL: str = Field(
    default=_DEFAULT_DB_PATH,
    description="Database connection string (SQLite or PostgreSQL)"
)
```

**Type**: `str`  
**Default**: `sqlite:///{PROJECT_ROOT}/analytics.db` (absolute path)  
**Formats**:
- SQLite: `sqlite:///path/to/db.db`
- PostgreSQL: `postgresql://user:pass@host:port/dbname`

**Example**:
```bash
DATABASE_URL=sqlite:///./analytics.db
# or
DATABASE_URL=postgresql://user:password@localhost/chatbot_db
```

---

### AWS S3 Settings (Optional)

All AWS settings are optional and only needed if using S3 for file storage.

#### AWS_ACCESS_KEY_ID
```python
AWS_ACCESS_KEY_ID: str = Field(default="changeme", ...)
```

**Type**: `str`  
**Required**: No  
**Default**: `"changeme"`

#### AWS_SECRET_ACCESS_KEY
```python
AWS_SECRET_ACCESS_KEY: str = Field(default="changeme", ...)
```

**Type**: `str`  
**Required**: No  
**Default**: `"changeme"`

**Validation**: Both keys have whitespace stripped automatically

#### AWS_REGION
```python
AWS_REGION: str = Field(default="us-east-1", ...)
```

**Type**: `str`  
**Default**: `"us-east-1"`

#### S3_BUCKET_NAME
```python
S3_BUCKET_NAME: str = Field(default="support-chatbot-kb", ...)
```

**Type**: `str`  
**Default**: `"support-chatbot-kb"`

---

### Pinecone Settings

#### PINECONE_ENV
```python
PINECONE_ENV: str = Field(default="us-east-1-aws", ...)
```

**Type**: `str`  
**Default**: `"us-east-1-aws"`  
**Options**: Check Pinecone dashboard for available environments

#### PINECONE_INDEX_NAME
```python
PINECONE_INDEX_NAME: str = Field(default="support-chatbot", ...)
```

**Type**: `str`  
**Default**: `"support-chatbot"`  
**Note**: Must match index name created in Pinecone dashboard

---

### SMTP Email Settings (Optional)

All SMTP settings are optional and only needed for email functionality.

#### SMTP_SERVER
```python
SMTP_SERVER: Optional[str] = Field(default=None, ...)
```

**Type**: `Optional[str]`  
**Default**: `None`  
**Example**: `"smtp.gmail.com"`

#### SMTP_PORT
```python
SMTP_PORT: int = Field(default=587, ...)
```

**Type**: `int`  
**Default**: `587` (TLS)  
**Common Values**: 587 (TLS), 465 (SSL), 25 (unencrypted)

#### SMTP_USERNAME
```python
SMTP_USERNAME: Optional[str] = Field(default=None, ...)
```

**Type**: `Optional[str]`  
**Default**: `None`

#### SMTP_PASSWORD
```python
SMTP_PASSWORD: Optional[str] = Field(default=None, ...)
```

**Type**: `Optional[str]`  
**Default**: `None`  
**Note**: For Gmail, use App Password, not account password

#### SMTP_FROM_EMAIL
```python
SMTP_FROM_EMAIL: str = Field(default="noreply@supportbot.com", ...)
```

**Type**: `str`  
**Default**: `"noreply@supportbot.com"`

---

## Field Validators

### validate_openai_key
```python
@field_validator('OPENAI_API_KEY')
@classmethod
def validate_openai_key(cls, v: str) -> str:
```

**Validation Rules**:
1. Strips leading/trailing whitespace
2. Checks if empty → raises `ValueError`
3. Checks format (must start with "sk-") → raises `ValueError`

**Error Messages**:
```
OPENAI_API_KEY is required. Set it in .env file.
Get your key at: https://platform.openai.com/api-keys
```

```
OPENAI_API_KEY format invalid. Should start with 'sk-'
Got: my-key-12...
```

---

### validate_pinecone_key
```python
@field_validator('PINECONE_API_KEY')
@classmethod
def validate_pinecone_key(cls, v: str) -> str:
```

**Validation Rules**:
1. Strips leading/trailing whitespace
2. Checks if empty → raises `ValueError`

**Error Message**:
```
PINECONE_API_KEY is required. Set it in .env file.
Get your key at: https://www.pinecone.io/
```

---

### strip_aws_secrets
```python
@field_validator('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')
@classmethod
def strip_aws_secrets(cls, v: str) -> str:
```

**Purpose**: Remove accidental whitespace from copy-paste

---

## Setup Instructions

### 1. Create .env File

Copy the example template:
```bash
cp .env.example .env
```

### 2. Get Required API Keys

**OpenAI**:
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)

**Pinecone**:
1. Sign up at https://www.pinecone.io/
2. Create a new project
3. Get API key from dashboard
4. Create an index (note the name)

### 3. Edit .env File

```bash
# Required
OPENAI_API_KEY=sk-proj-your-actual-key-here
PINECONE_API_KEY=your-pinecone-key-here

# Optional: Update if needed
PINECONE_INDEX_NAME=support-chatbot
DATABASE_URL=sqlite:///./analytics.db
```

### 4. Verify Setup

```python
from app.core.config import settings

# Will fail with clear error if keys missing
print(settings.OPENAI_API_KEY[:10])  # sk-proj-ab...
```

---

## Usage

### Import Settings

```python
from app.core.config import settings
```

**Singleton**: Same instance used throughout application

### Access Configuration

```python
# Required settings
api_key = settings.OPENAI_API_KEY
pinecone_key = settings.PINECONE_API_KEY

# Database
db_url = settings.DATABASE_URL

# Optional settings
if settings.SMTP_SERVER:
    # Email is configured
    send_email(settings.SMTP_SERVER, settings.SMTP_PORT)
```

### Testing with get_settings()

```python
from app.core.config import get_settings

# In tests, you can mock get_settings
def test_my_function(monkeypatch):
    mock_settings = MagicMock()
    mock_settings.OPENAI_API_KEY = "sk-test-key"
    monkeypatch.setattr('app.core.config.get_settings', lambda: mock_settings)
    # Test code here
```

---

## Best Practices

### 1. Never Commit .env

**✅ Good**:
```bash
# .gitignore
.env
.env.local
.env.production
```

**❌ Bad**: Committing `.env` to git exposes secrets

---

### 2. Use Environment Variables in Production

**Docker**:
```dockerfile
ENV OPENAI_API_KEY=sk-prod-key
ENV PINECONE_API_KEY=prod-pinecone-key
```

**Kubernetes**:
```yaml
env:
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: api-secrets
        key: openai-key
```

---

### 3. Validate Early

Settings are validated at import time. If keys are missing, the app fails **before** starting the server (not during first request).

**Benefits**:
- Fast feedback
- Clear error messages
- Prevents partial startups

---

### 4. Use Case-Sensitive Names

Environment variables must be UPPERCASE:

**✅ Good**:
```bash
OPENAI_API_KEY=sk-key
```

**❌ Bad**:
```bash
openai_api_key=sk-key  # Won't work!
```

---

### 5. Check Optional Settings

```python
# ✅ Good: Check before using
if settings.SMTP_SERVER:
    send_email()

# ❌ Bad: Assume it's set
email_client = SMTPClient(settings.SMTP_SERVER)  # Could be None!
```

---

## Troubleshooting

### Error: "OPENAI_API_KEY is required"

**Cause**: Missing or empty `OPENAI_API_KEY` in `.env`

**Solution**:
1. Create `.env` file if it doesn't exist
2. Add line: `OPENAI_API_KEY=sk-your-key-here`
3. Get key from https://platform.openai.com/api-keys

---

### Error: "OPENAI_API_KEY format invalid"

**Cause**: Key doesn't start with "sk-"

**Solution**:
1. Verify you copied the full key (not just part of it)
2. Ensure no quotes around the value in `.env`
3. Check for extra spaces: `OPENAI_API_KEY=sk-key` ✅ not `OPENAI_API_KEY= sk-key` ❌

---

### Error: "PINECONE_API_KEY is required"

**Cause**: Missing Pinecone key in `.env`

**Solution**:
1. Sign up at https://www.pinecone.io/
2. Get API key from dashboard
3. Add to `.env`: `PINECONE_API_KEY=your-key`

---

### Database file not found

**Cause**: Relative path `./analytics.db` depends on working directory

**Solution**: Use absolute path (already default now):
```bash
DATABASE_URL=sqlite:////absolute/path/to/analytics.db
```

---

### SMTP settings not working

**Cause**: SMTP fields are `None` by default

**Check**:
```python
if settings.SMTP_SERVER is None:
    print("SMTP not configured")
```

**Solution**: Set all SMTP fields in `.env`:
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-app-password
```

---

### Case-sensitive env var issues

**Cause**: `case_sensitive=True` requires uppercase

**Solution**: Use UPPERCASE in `.env`:
```bash
OPENAI_API_KEY=...  # ✅
openai_api_key=...  # ❌
```

---

## Related Documentation

- [OpenAI API Keys](https://platform.openai.com/api-keys)
- [Pinecone Setup](https://www.pinecone.io/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)


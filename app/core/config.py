"""
Application Configuration Settings.

This module defines all configuration settings loaded from environment variables.
Settings are loaded from .env file automatically using Pydantic BaseSettings.
"""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

load_dotenv()

# Project root for absolute paths
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_DB_PATH = f"sqlite:///{_PROJECT_ROOT}/analytics.db"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden by creating a .env file in the project root.
    See .env.example for template.
    
    Attributes:
        PROJECT_NAME: Display name of the application
        OPENAI_API_KEY: OpenAI API key for embeddings and chat (REQUIRED)
        DATABASE_URL: Database connection string (SQLite or PostgreSQL)
        AWS_ACCESS_KEY_ID: AWS access key for S3 storage (optional)
        AWS_SECRET_ACCESS_KEY: AWS secret key for S3 storage (optional)
        AWS_REGION: AWS region for S3 bucket
        S3_BUCKET_NAME: Name of S3 bucket for PDF storage
        PINECONE_API_KEY: Pinecone API key for vector search (REQUIRED)
        PINECONE_ENV: Pinecone environment (e.g., 'us-east-1-aws')
        PINECONE_INDEX_NAME: Name of Pinecone index
        SMTP_SERVER: SMTP server for email (optional)
        SMTP_PORT: SMTP port for email
        SMTP_USERNAME: SMTP username (optional)
        SMTP_PASSWORD: SMTP password (optional)
        SMTP_FROM_EMAIL: From email address
    """
    
    # Application
    PROJECT_NAME: str = Field(
        default="Support Chatbot",
        description="Display name of the application"
    )
    
    # OpenAI (REQUIRED)
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key for embeddings and LLM (REQUIRED)"
    )
    
    # Database
    DATABASE_URL: str = Field(
        default=_DEFAULT_DB_PATH,
        description="Database connection string (SQLite or PostgreSQL)"
    )
    
    # AWS S3 Configuration (Optional)
    AWS_ACCESS_KEY_ID: str = Field(
        default="changeme",
        description="AWS access key ID for S3 storage"
    )
    AWS_SECRET_ACCESS_KEY: str = Field(
        default="changeme",
        description="AWS secret access key for S3 storage"
    )
    AWS_REGION: str = Field(
        default="us-east-1",
        description="AWS region for S3 bucket"
    )
    S3_BUCKET_NAME: str = Field(
        default="support-chatbot-kb",
        description="Name of S3 bucket for knowledge base PDFs"
    )

    # Pinecone Vector Database (REQUIRED)
    PINECONE_API_KEY: str = Field(
        default="",
        description="Pinecone API key for vector search (REQUIRED)"
    )
    PINECONE_ENV: str = Field(
        default="us-east-1-aws",
        description="Pinecone environment identifier"
    )
    PINECONE_INDEX_NAME: str = Field(
        default="support-chatbot",
        description="Name of Pinecone index for embeddings"
    )

    # Email / SMTP Configuration (Optional)
    SMTP_SERVER: Optional[str] = Field(default=None, description="SMTP Server (e.g., smtp.gmail.com)")
    SMTP_PORT: int = Field(default=587, description="SMTP Port (e.g., 587)")
    SMTP_USERNAME: Optional[str] = Field(default=None, description="SMTP Username")
    SMTP_PASSWORD: Optional[str] = Field(default=None, description="SMTP Password")
    SMTP_FROM_EMAIL: str = Field(default="noreply@supportbot.com", description="From Email Address")
    
    # CORS Configuration (Production)
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:8000,http://127.0.0.1:8000",
        description="Comma-separated list of allowed CORS origins (e.g., 'https://yourdomain.com,https://www.yourdomain.com')"
    )

    # Pricing (GPT-4o-mini as of Dec 2024)
    INPUT_COST_PER_TOKEN: float = Field(default=0.00000015, description="Cost per input token")
    OUTPUT_COST_PER_TOKEN: float = Field(default=0.0000006, description="Cost per output token")
    EMBEDDING_COST_PER_TOKEN: float = Field(default=0.00000002, description="Cost per embedding token")
    
    # Field Validators
    @field_validator('OPENAI_API_KEY')
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """Validate OpenAI API key is set and has correct format."""
        v = v.strip() if v else ""
        if not v:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in .env file.\n"
                "Get your key at: https://platform.openai.com/api-keys"
            )
        if not v.startswith("sk-"):
            raise ValueError(
                "OPENAI_API_KEY format invalid. Should start with 'sk-'\n"
                f"Got: {v[:10]}..."
            )
        return v
    
    @field_validator('PINECONE_API_KEY')
    @classmethod
    def validate_pinecone_key(cls, v: str) -> str:
        """Validate Pinecone API key is set."""
        v = v.strip() if v else ""
        if not v:
            raise ValueError(
                "PINECONE_API_KEY is required. Set it in .env file.\n"
                "Get your key at: https://www.pinecone.io/"
            )
        return v
    
    @field_validator('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')
    @classmethod
    def strip_aws_secrets(cls, v: str) -> str:
        """Strip whitespace from AWS credentials."""
        return v.strip() if v else v
    
    # Security: Hardening Flags (Patch B)
    # These flags are opt-in security measures with NO behavior change when disabled
    SANITIZE_ERRORS: bool = Field(
        default=False,
        description="If True, sanitize exception details in API responses (prevents info leakage). Server logs still contain full traces."
    )
    
    STRICT_HISTORY_VALIDATION: bool = Field(
        default=False,
        description="If True, enforce strict validation on conversation_history structure to prevent DoS via pathological payloads."
    )
    
    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True  # Enforce uppercase env var names
    )


# Singleton settings instance
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

# For backwards compatibility
settings = get_settings()


"""Application configuration with Pydantic BaseSettings.

All configuration is read from environment variables with sensible defaults.
Sensitive values (API keys, database URLs, CORS origins) should be in .env (not committed).
"""

from enum import Enum
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings from environment variables.

    Pydantic BaseSettings automatically reads from .env file and environment.
    All sensitive values should be in .env (not committed to git).
    All non-sensitive defaults can be in .env.example.

    See .env.example for all available configuration options.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ========================================================================
    # App Configuration
    # ========================================================================

    APP_NAME: str = Field(default="nexus", description="Application name")
    ENV: Environment = Field(default=Environment.DEVELOPMENT, description="Environment")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # ========================================================================
    # Server Configuration
    # ========================================================================

    BACKEND_HOST: str = Field(default="0.0.0.0", description="Backend host to bind to")
    BACKEND_PORT: int = Field(default=8000, description="Backend port")

    # ========================================================================
    # CORS Configuration (CRITICAL FOR FRONTEND)
    # ========================================================================

    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
        ],
        description="Comma-separated or JSON list of allowed CORS origins",
    )

    # ========================================================================
    # Database
    # ========================================================================

    DATABASE_URL: str = Field(
        default="postgresql+psycopg://app_user:password@localhost:5432/nexus",
        description="PostgreSQL connection URL",
    )

    # ========================================================================
    # Redis
    # ========================================================================

    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # ========================================================================
    # Clerk OIDC Authentication
    # ========================================================================

    CLERK_JWKS_URL: str = Field(
        default="", description="Clerk JWKS endpoint URL for JWT validation"
    )
    CLERK_ISSUER: str = Field(default="", description="Clerk token issuer URL")

    # ========================================================================
    # LLM Provider Credentials (SENSITIVE - .env only)
    # ========================================================================

    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key (optional if not using OpenAI)",
    )
    ANTHROPIC_API_KEY: str = Field(
        default="",
        description="Anthropic API key (optional if not using Anthropic)",
    )
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API key (optional if not using Gemini)",
    )

    # ========================================================================
    # LLM Configuration
    # ========================================================================

    LLM_PROVIDER: str = Field(
        default="openai",
        description="Primary LLM provider: 'openai', 'anthropic', or 'gemini'",
    )
    LLM_MODEL: str = Field(
        default="gpt-4-turbo",
        description="Model name (e.g., gpt-4-turbo, claude-3-opus, gemini-2.0-flash)",
    )

    # ========================================================================
    # Embeddings Configuration
    # ========================================================================

    EMBEDDINGS_PROVIDER: str = Field(
        default="openai",
        description="Embeddings provider: 'openai' or 'local'",
    )
    EMBEDDINGS_MODEL: str = Field(
        default="text-embedding-3-small",
        description="Embeddings model name",
    )
    EMBEDDINGS_DIMENSION: int = Field(
        default=1536,
        description="Vector dimension (1536 for OpenAI text-embedding-3-*)",
    )

    # ========================================================================
    # Storage Configuration
    # ========================================================================

    STORAGE_BACKEND: str = Field(
        default="local",
        description="File storage backend: 'local' (filesystem) or 's3' (AWS S3)",
    )
    STORAGE_PATH: str = Field(
        default="./storage/documents",
        description="Local filesystem storage path (if STORAGE_BACKEND=local)",
    )
    S3_BUCKET: str = Field(
        default="",
        description="S3 bucket name (if STORAGE_BACKEND=s3)",
    )
    S3_REGION: str = Field(
        default="us-east-1",
        description="AWS region for S3",
    )

    # ========================================================================
    # Logging Configuration
    # ========================================================================

    LOG_LEVEL: str = Field(
        default="INFO",
        description="Python logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    LOG_FORMAT: str = Field(
        default="json",
        description="Log format: 'json' (structured) or 'text' (human-readable)",
    )

    # ========================================================================
    # Feature Flags
    # ========================================================================

    ENABLE_RAG: bool = Field(
        default=True,
        description="Enable RAG (Retrieval-Augmented Generation)",
    )
    ENABLE_EMBEDDINGS: bool = Field(
        default=True,
        description="Enable embedding generation",
    )

    # ========================================================================
    # Computed Properties
    # ========================================================================

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENV == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENV == Environment.DEVELOPMENT

    @property
    def is_staging(self) -> bool:
        """Check if running in staging."""
        return self.ENV == Environment.STAGING

    def get_database_url(self) -> str:
        """Get database URL, ensuring it's set."""
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable must be set")
        return self.DATABASE_URL

    def get_cors_origins(self) -> List[str]:
        """Get CORS origins, returning a defensive copy."""
        return list(self.CORS_ORIGINS)


# ============================================================================
# Singleton Settings Instance
# ============================================================================

_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Get the singleton Settings instance.

    This function implements lazy initialization of settings.
    Subsequent calls return the same cached instance.

    Returns:
        Configured Settings instance with values from .env and environment.
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

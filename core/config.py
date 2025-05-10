from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "mamba_db"
    DATABASE_URL: Optional[str] = None # Will be constructed if not provided

    # Valkey/Redis
    VALKEY_URL: Optional[str] = None # Keep this as Optional, might not always be configured

    # JWT Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 100

    # OpenAI (if needed directly from settings)
    OPENAI_API_KEY: Optional[str] = None 

    # ZeroBounce API Key
    ZEROBOUNCE_API_KEY: Optional[str] = None

    # Google OAuth Client ID
    GOOGLE_CLIENT_ID: Optional[str] = None

    # Default token limit for free users
    DEFAULT_FREE_USER_TOKEN_LIMIT: int = 800

    # Default password for users created via Google Sign-In
    GOOGLE_USER_DEFAULT_PASSWORD: str = "google_user_strong_default_password_#@!"

    # Add other environment variables here as needed
    SSL_CERT_FILE: Optional[str] = None # For certifi.where()

    def __init__(self, **values):
        super().__init__(**values)
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings() 
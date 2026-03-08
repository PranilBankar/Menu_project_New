"""
Environment Configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # App
    APP_NAME: str = "Menu Intelligence System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Database (Supabase)
    DATABASE_URL: str = "postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres?sslmode=require"
    DB_ECHO: bool = False
    
    # Supabase (Optional - for future features)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL: int = 3600  # 1 hour
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # OCR
    OCR_ENGINE: str = "paddleocr"  # paddleocr or google_vision
    GOOGLE_VISION_API_KEY: Optional[str] = None
    
    # LLM
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_TEMPERATURE: float = 0.3
    HUGGINGFACE_API_KEY: Optional[str] = None
    LLM_PROVIDER: Optional[str] = None
    
    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    
    # File Upload
    UPLOAD_DIR: str = "data/raw"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".pdf"}
    
    # CORS
    CORS_ORIGINS: list = [
        "*",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

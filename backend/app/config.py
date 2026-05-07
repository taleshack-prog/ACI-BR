"""
Configurações centralizadas via variáveis de ambiente (Pydantic Settings).
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────
    APP_NAME: str = "ACI-BR"
    DEBUG: bool = False
    API_VERSION: str = "v1"

    # ── Segurança ─────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production"
    JWT_SECRET: str = "change-me-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Banco de Dados ────────────────────────────────
    POSTGRES_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/aci_db"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "aci_staging"

    # ── Armazenamento de Áudio ────────────────────────
    AUDIO_STORAGE_BUCKET: str = "aci-audio-encrypted"
    AUDIO_TTL_HOURS: int = 24  # Descarte pós-processamento (LGPD)
    SESSION_TTL_DAYS: int = 30  # TTL MongoDB

    # ── Modelos ML ────────────────────────────────────
    WHISPER_MODEL: str = "large-v3"
    WHISPER_LANGUAGE: str = "pt"
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    NER_MODEL: str = "pucpr/biobertpt-clin"  # BioBERT pt-BR clínico
    HF_TOKEN: str = ""  # HuggingFace token para pyannote

    # ── FHIR ──────────────────────────────────────────
    FHIR_BASE_URL: str = "https://api.aci-br.com/fhir/r4"
    FHIR_VERSION: str = "4.0.1"

    # ── Review ────────────────────────────────────────
    REVIEW_TIMEOUT_HOURS: int = 24
    LOW_CONFIDENCE_THRESHOLD: float = 0.85

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

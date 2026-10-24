"""
Production configuration management for RakshakAI multi-tenant backend.
Loads environment variables and enforces validation and secret security.
"""
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Environment
    ENV: str = Field(default="dev", description="dev | test | prod")

    # Database
    MONGODB_URI: Optional[str] = Field(default=None, description="MongoDB Atlas connection URI")
    MONGODB_DB: str = Field(default="rakshakai", description="MongoDB Database name")
    USE_MOCK_DB: bool = Field(default=False, description="Use mongomock-motor for offline execution")

    # JWT Authentication
    JWT_SECRET: str = Field(
        default="rakshakai_production_secure_jwt_secret_key_minimum_32_characters",
        description="HMAC secret key for JWT access tokens",
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_TTL_MIN: int = Field(default=15, description="Access token expiration in minutes")
    REFRESH_TOKEN_TTL_DAYS: int = Field(default=7, description="Refresh token expiration in days")
    JWT_ISSUER: str = Field(default="rakshakai")
    JWT_AUDIENCE: str = Field(default="rakshakai-api")

    # Cryptography & Pseudonymization
    PSEUDONYM_SALT: str = Field(
        default="rakshak_campus_pseudonymization_salt_2026_secure",
        description="Salt for irreversible SHA-256 card & identifier pseudonymization",
    )

    # Networking & CORS
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    CORS_ORIGINS: str = Field(default="http://localhost:5173", description="Comma-separated CORS origins")
    FRONTEND_URL: str = Field(default="http://localhost:5173")

    # Rate Limiting & Detection
    RATE_LIMIT_LOGIN: str = Field(default="5/minute")
    DETECTOR_MODE: str = Field(default="mock", description="mock | real")
    FIGHT_DETECTION: bool = Field(default=True, description="Enable experimental fight detection heuristic")
    AUDIO_CLASSIFIER: str = Field(default="yamnet", description="yamnet | yamnet_head")
    HELP_KEYWORDS: bool = Field(default=False, description="Spot emergency keywords via speech model")

    MAX_UPLOAD_SIZE_MB: int = Field(default=200, description="Max allowed file upload size in MB")
    SHOW_BOXES: bool = Field(default=True, description="Draw tracked person bounding boxes on visualisations")

    # Filesystem Paths
    PROJECT_ROOT: Path = PROJECT_ROOT
    RULES_DEFAULT_PATH: Path = BACKEND_DIR / "rules.default.yaml"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    EVIDENCE_DIR: Path = PROJECT_ROOT / "data" / "evidence"
    SCENARIOS_DIR: Path = PROJECT_ROOT / "data" / "scenarios"
    ACCESS_LOGS_DIR: Path = PROJECT_ROOT / "data" / "access_logs"
    UPLOADS_DIR: Path = PROJECT_ROOT / "data" / "uploads"
    EVAL_DIR: Path = PROJECT_ROOT / "data" / "eval"
    ML_DIR: Path = PROJECT_ROOT / "ml"
    MODELS_DIR: Path = PROJECT_ROOT / "ml" / "models"
    EVAL_RESULTS_DIR: Path = PROJECT_ROOT / "ml" / "eval" / "results"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long for cryptographic security.")
        return v

    def validate_prod_secrets(self) -> None:
        """Enforce strict secret safety when running in production."""
        if self.ENV == "prod":
            if not self.MONGODB_URI or "localhost" in self.MONGODB_URI:
                raise ValueError("In production, MONGODB_URI must be provided and point to a production cluster.")
            if "default" in self.JWT_SECRET or len(self.JWT_SECRET) < 32:
                raise ValueError("In production, JWT_SECRET must be a strong, non-default random secret.")
            if "default" in self.PSEUDONYM_SALT:
                raise ValueError("In production, PSEUDONYM_SALT must be configured securely.")

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

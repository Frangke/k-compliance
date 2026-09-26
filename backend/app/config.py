from pathlib import Path

from pydantic_settings import BaseSettings

# .env is in project root (one level above backend/)
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Password Policy (ISMS-P 2.5.4)
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_COMPLEXITY: bool = True
    PASSWORD_HISTORY_COUNT: int = 3

    # Account Lockout (ISMS-P 2.5.3)
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30

    # Session
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30

    # S3
    S3_BUCKET_NAME: str = "k-compliance-evidence-dev"
    S3_REGION: str = "ap-northeast-2"

    # Encryption (cloud_accounts credentials AES-256-GCM)
    ENCRYPTION_KEY: str

    # Prowler
    PROWLER_BIN_PATH: str = "prowler"
    PROWLER_OUTPUT_DIR: str = "/tmp/prowler-scans"
    PROWLER_TIMEOUT_SECONDS: int = 3600  # hard ceiling for a single scan subprocess

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": str(_env_file), "env_file_encoding": "utf-8"}


settings = Settings()

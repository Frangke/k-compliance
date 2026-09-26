from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

# .env is in project root (one level above backend/)
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"


class SSMParameterStoreSource(PydanticBaseSettingsSource):
    """Load settings from AWS SSM Parameter Store under SSM_PARAMETER_PREFIX.

    Each parameter's last path segment is the setting name, e.g.
    /k-compliance/prod/JWT_SECRET_KEY -> JWT_SECRET_KEY. SecureString values
    are decrypted. Credentials come from the default boto3 chain (EC2 instance
    profile), so no AWS keys are stored on the host.

    Disabled when SSM_PARAMETER_PREFIX is unset (local dev / CI). When it is
    set, any failure aborts startup rather than running without secrets.
    """

    def get_field_value(self, field, field_name):  # unused; __call__ loads everything at once
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        prefix = self.current_state.get("SSM_PARAMETER_PREFIX")
        if not prefix:
            return {}
        region = self.current_state.get("SSM_REGION") or "ap-northeast-2"

        import boto3

        client = boto3.client("ssm", region_name=region)
        path = prefix.rstrip("/") + "/"
        values: dict[str, Any] = {}
        for page in client.get_paginator("get_parameters_by_path").paginate(
            Path=path, Recursive=False, WithDecryption=True
        ):
            for param in page["Parameters"]:
                name = param["Name"][len(path) :]
                if name in self.settings_cls.model_fields:
                    values[name] = param["Value"]
        return values


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

    # SSM Parameter Store (EC2: secrets from instance profile instead of .env)
    SSM_PARAMETER_PREFIX: str | None = None
    SSM_REGION: str = "ap-northeast-2"

    # Prowler
    PROWLER_BIN_PATH: str = "prowler"
    PROWLER_OUTPUT_DIR: str = "/tmp/prowler-scans"
    PROWLER_TIMEOUT_SECONDS: int = 3600  # hard ceiling for a single scan subprocess

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": str(_env_file), "env_file_encoding": "utf-8"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Environment and .env win over SSM, so a local override still works.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            SSMParameterStoreSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()

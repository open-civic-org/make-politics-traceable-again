from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    database_url: str = "postgresql+psycopg://mpta:mpta_dev_password@localhost:5432/mpta"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "mpta-raw"
    s3_region: str = "us-east-1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_public_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    eci_live_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("MPTA_ECI_LIVE_ENABLED", "eci_live_enabled"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

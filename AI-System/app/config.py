from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "LocalAI Control"
    app_env: Literal["development", "production", "test"] = "development"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'localai.db'}"
    secret_key: str = Field(default="change-me-before-production", min_length=16)
    allowed_hosts: str = "localhost,127.0.0.1"
    trusted_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    force_https: bool = False
    session_hours: int = Field(default=24, ge=1, le=720)
    max_login_attempts: int = Field(default=6, ge=3, le=30)
    login_lock_minutes: int = Field(default=15, ge=1, le=1440)
    request_rate_per_minute: int = Field(default=120, ge=10, le=5000)

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    model_context_length: int = Field(default=8192, ge=1024, le=262144)
    model_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    model_max_tokens: int = Field(default=2048, ge=64, le=32768)

    searxng_url: str = "http://127.0.0.1:8080"
    research_max_results: int = Field(default=6, ge=1, le=20)
    research_max_pages: int = Field(default=5, ge=1, le=15)
    research_timeout_seconds: float = Field(default=12.0, ge=2.0, le=60.0)
    research_max_download_mb: int = Field(default=8, ge=1, le=100)
    research_user_agent: str = "LocalAI-Control/1.0 (+local-research-assistant)"

    upload_dir: Path = BASE_DIR / "data" / "uploads"
    project_dir: Path = BASE_DIR / "data" / "projects"
    backup_dir: Path = BASE_DIR / "data" / "backups"
    max_upload_gb: float = Field(default=5.0, gt=0.0, le=20.0)
    archive_max_files: int = Field(default=5000, ge=10, le=100000)
    archive_max_expanded_gb: float = Field(default=10.0, gt=0.0, le=100.0)
    archive_max_depth: int = Field(default=2, ge=0, le=5)
    clamav_host: str = ""
    clamav_port: int = 3310

    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    @field_validator("upload_dir", "project_dir", "backup_dir", mode="before")
    @classmethod
    def resolve_path(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def hosts(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.trusted_origins.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_gb * 1024**3)

    @property
    def archive_max_expanded_bytes(self) -> int:
        return int(self.archive_max_expanded_gb * 1024**3)

    def validate_production(self) -> None:
        if self.app_env == "production" and self.secret_key == "change-me-before-production":
            raise RuntimeError("SECRET_KEY must be changed in production")
        if self.app_env == "production" and not self.force_https:
            raise RuntimeError("FORCE_HTTPS must be enabled in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    for directory in (settings.upload_dir, settings.project_dir, settings.backup_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return settings

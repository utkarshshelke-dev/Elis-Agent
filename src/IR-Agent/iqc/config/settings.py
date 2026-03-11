"""
Module: config/settings.py
Description: Centralised settings for IQC Agent.
Author: IQC Team
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).parent.parent / ".env"
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    db_host: str = "34.69.99.159"
    db_port: int = 5432
    db_user: str = "postgres"
    db_pass: str = ""
    db_name: str = "grid_os_poc"

    google_cloud_project: str = "the-grid-os"
    vertex_location:      str = "us-central1"
    vertex_model:         str = "gemini-2.0-flash"

    log_level: str = "INFO"
    log_dir:   str = "logs"
    port:      int = 8080

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def db_dsn(self) -> dict:
        return {
            "host":     self.db_host,
            "port":     self.db_port,
            "user":     self.db_user,
            "password": self.db_pass,
            "dbname":   self.db_name,
        }


settings = Settings()
__all__ = ["settings", "Settings"]
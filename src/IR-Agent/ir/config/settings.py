"""
Module: config/settings.py
Description: Centralised settings for IR Domain Agent.
Author: IR Team
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).parent.parent / ".env"
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    google_cloud_project:  str = "the-grid-os"
    google_cloud_location: str = "us-central1"

    iqc_engine_id: str = "6728420724245004288"

    db_host: str = "34.69.99.159"
    db_port: int = 5432
    db_user: str = "postgres"
    db_pass: str = ""
    db_name: str = "grid_os_poc"

    session_ttl: int = 3600
    log_level:   str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def iqc_base_url(self) -> str:
        return (
            f"https://{self.google_cloud_location}-aiplatform.googleapis.com"
            f"/v1beta1/projects/{self.google_cloud_project}"
            f"/locations/{self.google_cloud_location}/reasoningEngines"
        )

    @property
    def iqc_stream_url(self) -> str:
        return f"{self.iqc_base_url}/{self.iqc_engine_id}:streamQuery"

    @property
    def iqc_query_url(self) -> str:
        return f"{self.iqc_base_url}/{self.iqc_engine_id}:query"

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
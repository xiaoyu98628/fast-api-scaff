from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="WORKER_", frozen=True, allow_inf_nan=False)
    concurrency: int = Field(default=4, ge=1, le=1024)
    shutdown_timeout_seconds: float = Field(default=30.0, gt=0)

import re
from pathlib import Path

from config.logging import LoggingConfig
from paths import BASE_DIR


def slugify_app_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "app"


def resolve_level(settings: LoggingConfig, *, app_debug: bool) -> str:
    if settings.level is not None:
        return settings.level
    return "DEBUG" if app_debug else "INFO"


def log_dir(settings: LoggingConfig, app_name: str) -> Path:
    base = Path(settings.dir)
    if not base.is_absolute():
        base = BASE_DIR / base
    return base / slugify_app_name(app_name)

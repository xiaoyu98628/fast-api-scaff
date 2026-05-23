from pydantic_settings import SettingsConfigDict

from paths import ENV_FILE

BASE_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
)

"""保存所有环境配置模型共用的读取规则。"""

from pydantic_settings import SettingsConfigDict

from app.runtime.paths import ENV_FILE

# 多个配置模型共享同一份 .env，因此各模型忽略属于其他前缀的字段。
BASE_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
)

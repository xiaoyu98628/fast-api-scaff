"""日志 env 配置 + channels 声明（对齐 Laravel ``config/logging.php``）。"""

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.app import AppConfig
from config.settings import BASE_SETTINGS_CONFIG
from paths import BASE_DIR


class LogChannel(BaseModel):
    """单个日志通道：logger 名称 + 写入策略 + 级别 + 完整路径。"""

    logger: str
    path: str
    level: str
    driver: str = "single"
    console: bool = False
    also: list[str] = Field(default_factory=list)


class LoggingConfig(BaseSettings):
    """``LOG_`` 前缀；通道装配见 ``infrastructure/logging/manager``。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="LOG_",
    )

    level: str = Field(default="DEBUG")
    driver: str = Field(default="single")
    json_enabled: bool = Field(default=False, validation_alias=AliasChoices("JSON", "JSON_ENABLED"))
    console_enabled: bool = Field(default=True, validation_alias=AliasChoices("CONSOLE_ENABLED", "CONSOLE"))
    max_bytes: int = Field(default=10 * 1024 * 1024)
    backup_count: int = Field(default=5)

    @property
    def channels(self) -> dict[str, LogChannel]:
        """各通道完整日志路径在此定义，可按需单独修改 ``path``。"""
        app = AppConfig()

        return {
            "app": LogChannel(
                logger="app",
                driver=self.driver,
                level=self.level,
                path=str(BASE_DIR / "storage/logs" / app.name / "app.log"),
                console=True,
            ),
            "request": LogChannel(
                logger="app.request",
                driver=self.driver,
                level=self.level,
                path=str(BASE_DIR / "storage/logs" / app.name / "request.log"),
            ),
            "db": LogChannel(
                logger="sqlalchemy.engine",
                driver=self.driver,
                level=self.level,
                path=str(BASE_DIR / "storage/logs" / app.name / "db.log"),
                also=["sqlalchemy.pool"],
            ),
            "exception": LogChannel(
                logger="app.channel.exception",
                driver=self.driver,
                level=self.level,
                path=str(BASE_DIR / "storage/logs" / app.name / "exception.log"),
            ),
        }

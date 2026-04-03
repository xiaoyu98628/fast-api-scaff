from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR

class DatabaseSettings(BaseSettings):
    """应用配置。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = "127.0.0.1"
    db_port: str = "3306"
    db_database: str = 'fast-api'
    db_username: str = "root"
    db_password: str = "root"

    @property
    def database_url(self) -> str:
        """数据库连接地址。"""
        return f"mysql+asyncpg://{self.db_username}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_database}"
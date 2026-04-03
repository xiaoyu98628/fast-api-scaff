from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR

class DatabaseSettings(BaseSettings):
    """应用配置。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="DB_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: str = "3306"
    database: str = 'fast-api'
    username: str = "root"
    password: str = "root"

    @property
    def url(self) -> str:
        """数据库连接 URL（异步）"""
        # 根据驱动选择，这里使用 aiomysql
        return f"mysql+aiomysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?charset=utf8mb4"

    @property
    def sync_url(self) -> str:
        """同步数据库连接 URL（用于 Alembic 等工具）"""
        return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
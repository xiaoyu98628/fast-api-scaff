
from pydantic import BaseModel

from config.app import AppConfig


class Config(BaseModel):

    app: AppConfig


def config() -> Config:
    """获取配置。"""
    return Config(
        app=AppConfig()
    )

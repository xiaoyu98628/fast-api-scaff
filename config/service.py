"""服务级环境变量（无前缀）：如 ``SERVICE_CODE``（九位错误码中的 SS）。"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class ServiceSettings(BaseSettings):
    """与单服务部署相关的配置；``service_code`` 自环境变量 ``SERVICE_CODE`` 读取。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_code: str = Field(default="01", description="两位服务码，如 01、02、03。")

    @field_validator("service_code")
    @classmethod
    def validate_service_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 2:
            raise ValueError("SERVICE_CODE 必须是两位数字（如 01）")
        return value

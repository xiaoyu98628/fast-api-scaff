"""实现写入标准输出或标准错误的内置日志驱动。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.infrastructure.logging.contracts.driver import LoggingHandlerConfig


class StreamLoggingSettings(BaseModel):
    """描述 stream 驱动允许接受的严格配置。"""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    driver: Literal["stream"]
    stream: Literal["stdout", "stderr"] = "stdout"


def build_stream_handler(raw_config: dict[str, object]) -> LoggingHandlerConfig:
    """校验 stream 驱动配置并构建标准库 Handler 配置。"""

    settings = StreamLoggingSettings.model_validate(raw_config)

    return {
        "class": "logging.StreamHandler",
        "stream": f"ext://sys.{settings.stream}",
    }

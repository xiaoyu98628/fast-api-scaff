"""把 Console 结果和错误渲染到约定的标准流。"""

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from uuid import UUID

import typer
from pydantic import ValidationError


class ConsolePresenter:
    """将 Console 结果和错误写入约定的标准流。"""

    def result(self, value: object) -> None:
        """把结构化命令结果以单行 JSON 写入 stdout。"""

        typer.echo(json.dumps(value, ensure_ascii=False, default=_json_default))

    def text(self, value: str) -> None:
        """把无需结构化的普通文本写入 stdout。"""

        typer.echo(value)

    def error(self, error: Exception | str) -> None:
        """把适合用户阅读的错误写入 stderr。"""

        typer.echo(f"Error: {_format_error(error)}", err=True)


def _json_default(value: object) -> object:
    """转换 Console 契约允许输出的非原生 JSON 类型。"""

    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    raise TypeError(f"{type(value).__name__} 不能序列化为 JSON")


def _format_error(error: Exception | str) -> str:
    """把配置校验错误或普通异常转换为简洁文本。"""

    if isinstance(error, str):
        return error

    if isinstance(error, ValidationError):
        # 只展示第一条错误且排除输入值，避免配置秘密出现在终端输出中。
        first_error = error.errors(include_url=False, include_context=False, include_input=False)[0]
        location = ".".join(str(part) for part in first_error["loc"])
        prefix = f"配置 {location}" if location else "配置"
        return f"{prefix}：{first_error['msg']}"

    return str(error)

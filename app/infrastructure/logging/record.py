"""提供业务代码创建结构化日志扩展字段的辅助函数。"""

from enum import StrEnum


def log_extra(
    event: StrEnum | str,
    /,
    **details: object,
) -> dict[str, object]:
    """构建统一的结构化日志扩展字段。"""

    # details 保持嵌套，防止业务字段与 logging 内置 LogRecord 属性冲突。
    return {
        "event": event,
        "details": details,
    }

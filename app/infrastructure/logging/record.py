from enum import StrEnum


def log_extra(
    event: StrEnum | str,
    /,
    **details: object,
) -> dict[str, object]:
    """构建统一的结构化日志扩展字段。"""
    return {
        "event": event,
        "details": details,
    }

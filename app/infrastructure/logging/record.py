"""提供业务代码创建结构化日志扩展字段的辅助函数。"""

from enum import StrEnum

type ExceptionStackFrame = dict[str, str | int]


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


def safe_exception_details(error: BaseException) -> tuple[str, tuple[ExceptionStackFrame, ...]]:
    """提取异常类型和调用栈位置，不包含异常消息、局部变量或业务数据。"""

    error_type = f"{type(error).__module__}.{type(error).__qualname__}"
    frames: list[ExceptionStackFrame] = []
    current_traceback = error.__traceback__

    while current_traceback is not None:
        frame = current_traceback.tb_frame
        frames.append(
            {
                "module": frame.f_globals.get("__name__", "<unknown>"),
                "function": frame.f_code.co_qualname,
                "line": current_traceback.tb_lineno,
            }
        )
        current_traceback = current_traceback.tb_next

    return error_type, tuple(frames)

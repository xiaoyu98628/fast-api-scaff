"""跨模块通用业务码（XXXXX）；完整九位码由 ErrorCodeBuilder 统一构造。"""

from enum import IntEnum

class ErrorCode(IntEnum):
    """通用错误业务码（5位以内），不含 SS 与 AA。"""

    NOT_FOUND = 404
    INTERNAL_ERROR = 500

    def message(self) -> str:
        return {
            ErrorCode.NOT_FOUND: "资源不存在",
            ErrorCode.INTERNAL_ERROR: "系统异常",
        }[self]

    def status_code(self) -> int:
        return {
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.INTERNAL_ERROR: 500,
        }[self]

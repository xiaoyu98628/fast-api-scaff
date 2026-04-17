"""跨模块通用错误低位（BB×100+CC）；完整十位码由 ErrorCodeBuilder 统一构造。"""

from enum import IntEnum


class ErrorCode(IntEnum):
    """通用错误低位（模块+具体，不含 HTTP 前缀与服务码）。"""

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

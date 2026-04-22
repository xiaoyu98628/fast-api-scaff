"""跨模块通用错误低位（BB×100+CC）；完整十位码由 ErrorCodeBuilder 统一构造。"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """通用错误低位（模块+具体，不含 HTTP 前缀与服务码）。"""

    # 400
    REQUEST_ERROR = "0101"

    # 403
    FORBIDDEN_ERROR = "0101"

    # 404
    NOT_FOUND = "0101"

    # 422
    PARAMETER_ERROR = "0101"

    # 500
    INTERNAL_ERROR = "0500"

    def message(self) -> str:
        return {
            ErrorCode.REQUEST_ERROR: "请求错误",
            ErrorCode.FORBIDDEN_ERROR: "无权限访问",
            ErrorCode.NOT_FOUND: "资源不存在",
            ErrorCode.PARAMETER_ERROR: "参数错误",
            ErrorCode.INTERNAL_ERROR: "系统异常",
        }[self]

    def status_code(self) -> int:
        return {
            ErrorCode.REQUEST_ERROR: 400,
            ErrorCode.FORBIDDEN_ERROR: 403,
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.PARAMETER_ERROR: 422,
            ErrorCode.INTERNAL_ERROR: 500,
        }[self]

"""用户模块业务错误码定义（code + message + status_code）。"""

from enum import IntEnum


class UserErrorCode(IntEnum):
    """用户业务码低位（BB×100+CC，与 HTTP 状态由成员语义决定）。"""

    USER_NOT_EXIST = 1001
    USER_ALREADY_EXIST = 1002
    LOGIN_FAILED = 1003

    def message(self) -> str:
        return {
            UserErrorCode.USER_NOT_EXIST: "用户不存在",
            UserErrorCode.USER_ALREADY_EXIST: "用户已存在",
            UserErrorCode.LOGIN_FAILED: "用户名或密码错误",
        }[self]

    def status_code(self) -> int:
        return {
            UserErrorCode.USER_NOT_EXIST: 404,
            UserErrorCode.USER_ALREADY_EXIST: 400,
            UserErrorCode.LOGIN_FAILED: 401,
        }[self]

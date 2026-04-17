"""用户模块业务错误码定义（code + message + status_code）。"""

from enum import IntEnum


class UserErrorCode(IntEnum):
    """用户业务码低位（BB×100+CC，与 HTTP 状态由成员语义决定）。"""

    USER_NOT_EXIST = 1001
    USER_ALREADY_EXIST = 1002
    LOGIN_FAILED = 1003
    TOKEN_MISSING = 1004
    TOKEN_INVALID = 1005
    USER_UPDATE_NO_FIELDS = 1006

    def message(self) -> str:
        return {
            UserErrorCode.USER_NOT_EXIST: "用户不存在",
            UserErrorCode.USER_ALREADY_EXIST: "用户已存在",
            UserErrorCode.LOGIN_FAILED: "用户名或密码错误",
            UserErrorCode.TOKEN_MISSING: "未登录或缺少访问令牌",
            UserErrorCode.TOKEN_INVALID: "登录已失效，请重新登录",
            UserErrorCode.USER_UPDATE_NO_FIELDS: "至少需要更新昵称或密码中的一项",
        }[self]

    def status_code(self) -> int:
        return {
            UserErrorCode.USER_NOT_EXIST: 404,
            UserErrorCode.USER_ALREADY_EXIST: 400,
            UserErrorCode.LOGIN_FAILED: 401,
            UserErrorCode.TOKEN_MISSING: 401,
            UserErrorCode.TOKEN_INVALID: 401,
            UserErrorCode.USER_UPDATE_NO_FIELDS: 400,
        }[self]

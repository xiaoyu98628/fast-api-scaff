"""用户模块业务错误码。"""

from enum import IntEnum


class UserErrorCode(IntEnum):
    """用户业务码低位（与 HTTP 状态由成员语义决定）。"""

    USER_NOT_EXIST = 1001
    USER_ALREADY_EXIST = 1002
    LOGIN_FAILED = 1003
    TOKEN_MISSING = 1004
    TOKEN_INVALID = 1005
    USER_UPDATE_NO_FIELDS = 1006
    USER_STATUS_INVALID = 1007
    USER_STATUS_LOCKED = 1008

    def message(self) -> str:
        return {
            UserErrorCode.USER_NOT_EXIST: "用户不存在",
            UserErrorCode.USER_ALREADY_EXIST: "用户已存在",
            UserErrorCode.LOGIN_FAILED: "用户名或密码错误",
            UserErrorCode.TOKEN_MISSING: "未登录或缺少访问令牌",
            UserErrorCode.TOKEN_INVALID: "登录已失效，请重新登录",
            UserErrorCode.USER_UPDATE_NO_FIELDS: "至少需要更新昵称或密码中的一项",
            UserErrorCode.USER_STATUS_INVALID: "用户状态非法，仅支持 activation 或 locking",
            UserErrorCode.USER_STATUS_LOCKED: "账号已停用，请联系管理员",
        }[self]

    def status_code(self) -> int:
        return {
            UserErrorCode.USER_NOT_EXIST: 404,
            UserErrorCode.USER_ALREADY_EXIST: 400,
            UserErrorCode.LOGIN_FAILED: 401,
            UserErrorCode.TOKEN_MISSING: 401,
            UserErrorCode.TOKEN_INVALID: 401,
            UserErrorCode.USER_UPDATE_NO_FIELDS: 400,
            UserErrorCode.USER_STATUS_INVALID: 400,
            UserErrorCode.USER_STATUS_LOCKED: 403,
        }[self]

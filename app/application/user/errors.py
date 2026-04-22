"""用户模块业务错误码定义（code + message + status_code）。"""

from enum import StrEnum


class UserErrorCode(StrEnum):
    """用户业务码低位（BB×100+CC，与 HTTP 状态由成员语义决定）。"""

    USER_NOT_EXIST = "0101"
    USER_ALREADY_EXIST = "0102"
    LOGIN_FAILED = "0103"
    TOKEN_MISSING = "0104"
    TOKEN_INVALID = "0105"
    USER_UPDATE_NO_FIELDS = "0106"
    USER_STATUS_INVALID = "0107"
    USER_STATUS_LOCKED = "0108"

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

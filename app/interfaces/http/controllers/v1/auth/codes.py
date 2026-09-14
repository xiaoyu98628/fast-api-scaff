"""定义认证 HTTP API 专用的局部错误码。"""

from app.interfaces.http.shared.response.codes.contract import CodeDefinition, CodedEnum


class AuthErrorCode(CodedEnum):
    """区分登录凭据失败和连续失败触发的临时锁定。"""

    INVALID_CREDENTIALS = CodeDefinition(code="1101", message="用户名或密码错误", status_code=401)
    LOGIN_TEMPORARILY_LOCKED = CodeDefinition(code="1102", message="登录失败次数过多，已临时锁定", status_code=429)

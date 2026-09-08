"""把认证应用层异常映射为 HTTP 边界异常。"""

from app.contexts.user.application.auth_errors import (
    AuthApplicationError,
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LoginUserNotFoundError,
)
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.shared.response.codes.error_code import ErrorCode


def auth_error_to_http(error: AuthApplicationError) -> HttpError:
    """为已知认证错误选择状态码、公开文案和安全响应头。"""

    if isinstance(error, LoginUserNotFoundError):
        return HttpError(ErrorCode.RESOURCE_NOT_FOUND, message="用户不存在", headers={"Cache-Control": "no-store"})

    if isinstance(error, InvalidCredentialsError):
        message = "用户名或密码错误"
    elif isinstance(error, AuthenticationRequiredError):
        message = None
    else:
        raise TypeError(f"不支持的认证边界异常: {type(error).__name__}")

    # 认证失败同时声明 Bearer 方案，并禁止中间缓存保存凭据相关响应。
    return HttpError(
        ErrorCode.UNAUTHORIZED,
        message=message,
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )

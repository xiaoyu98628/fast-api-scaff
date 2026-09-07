from app.contexts.user.application.auth_errors import (
    AuthApplicationError,
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LoginUserNotFoundError,
)
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.shared.response.codes.error_code import ErrorCode


def auth_error_to_http(error: AuthApplicationError) -> HttpError:
    if isinstance(error, LoginUserNotFoundError):
        return HttpError(ErrorCode.RESOURCE_NOT_FOUND, message="用户不存在", headers={"Cache-Control": "no-store"})

    if isinstance(error, InvalidCredentialsError):
        message = "用户名或密码错误"
    elif isinstance(error, AuthenticationRequiredError):
        message = None
    else:
        raise TypeError(f"不支持的认证边界异常: {type(error).__name__}")

    return HttpError(
        ErrorCode.UNAUTHORIZED,
        message=message,
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )

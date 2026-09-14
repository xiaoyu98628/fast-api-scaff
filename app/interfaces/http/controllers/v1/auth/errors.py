"""把认证应用层异常映射为 HTTP 边界异常。"""

from app.contexts.user.application.auth_errors import (
    AuthApplicationError,
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LoginTemporarilyLockedError,
)
from app.interfaces.http.controllers.v1.auth.codes import AuthErrorCode
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.shared.response.codes.error_code import ErrorCode


def auth_error_to_http(error: AuthApplicationError) -> HttpError:
    """为已知认证错误选择状态码、公开文案和安全响应头。"""

    if isinstance(error, LoginTemporarilyLockedError):
        return HttpError(
            AuthErrorCode.LOGIN_TEMPORARILY_LOCKED,
            message=f"登录失败次数过多，已临时锁定，请在 {error.retry_after_seconds} 秒后重试",
            data={"retry_after_seconds": error.retry_after_seconds},
            headers={
                "Retry-After": str(error.retry_after_seconds),
                "Cache-Control": "no-store",
            },
        )

    if isinstance(error, InvalidCredentialsError):
        message = AuthErrorCode.INVALID_CREDENTIALS.message
        data = None
        if error.remaining_attempts is not None:
            message = f"{message}，还可尝试 {error.remaining_attempts} 次"
            data = {"remaining_attempts": error.remaining_attempts}
        return HttpError(
            AuthErrorCode.INVALID_CREDENTIALS,
            message=message,
            data=data,
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        )

    if not isinstance(error, AuthenticationRequiredError):
        raise TypeError(f"不支持的认证边界异常: {type(error).__name__}")

    # 会话认证失败声明 Bearer 方案，并禁止中间缓存保存凭据相关响应。
    return HttpError(
        ErrorCode.UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )

"""把用户领域与应用层错误映射为 HTTP 边界异常。"""

from app.contexts.user.application.errors import UserApplicationError, UserConflictError, UserNotFoundError
from app.contexts.user.domain.errors import InvalidUserDataError, UserDomainError
from app.interfaces.http.controllers.v1.users.codes import UserErrorCode
from app.interfaces.http.exceptions.error import HttpError

type UserBoundaryError = UserApplicationError | UserDomainError


def user_error_to_http(error: UserBoundaryError) -> HttpError:
    """为已知用户错误选择稳定的局部响应码和公开消息。"""

    if isinstance(error, UserNotFoundError):
        return HttpError(UserErrorCode.USER_NOT_FOUND)

    if isinstance(error, UserConflictError):
        code = {
            "username": UserErrorCode.USERNAME_CONFLICT,
            "email": UserErrorCode.EMAIL_CONFLICT,
        }[error.field]
        return HttpError(code)

    if isinstance(error, InvalidUserDataError):
        return HttpError(UserErrorCode.INVALID_USER_DATA, message=str(error))

    # 新增边界异常时必须显式决定 HTTP 语义，不能静默退化为错误映射。
    raise TypeError(f"不支持的用户边界异常: {type(error).__name__}")

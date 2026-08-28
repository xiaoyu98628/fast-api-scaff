from app.contexts.user.application.errors import UserApplicationError, UserConflictError, UserNotFoundError
from app.contexts.user.domain.errors import InvalidUserDataError, UserDomainError
from app.interfaces.http.controllers.v1.users.codes import UserErrorCode
from app.interfaces.http.exceptions.error import HttpError

type UserBoundaryError = UserApplicationError | UserDomainError


def user_error_to_http(error: UserBoundaryError) -> HttpError:
    if isinstance(error, UserNotFoundError):
        return HttpError(UserErrorCode.USER_NOT_FOUND)

    if isinstance(error, UserConflictError):
        code = {
            "username": UserErrorCode.USERNAME_CONFLICT,
            "email": UserErrorCode.EMAIL_CONFLICT,
            "identity": UserErrorCode.IDENTITY_CONFLICT,
        }[error.field]
        return HttpError(code)

    if isinstance(error, InvalidUserDataError):
        return HttpError(UserErrorCode.INVALID_USER_DATA, message=str(error))

    raise TypeError(f"不支持的用户边界异常: {type(error).__name__}")

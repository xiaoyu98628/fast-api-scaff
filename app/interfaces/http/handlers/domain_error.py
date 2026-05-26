import logging

from app.domain.user.exceptions import DomainError, InvalidUserUpdateError, UsernameAlreadyExistsError, UserNotFoundError
from app.interfaces.http.support.response.code.error_code import ErrorCode
from app.interfaces.http.support.response.json import JsonResponse

logger = logging.getLogger("app.channel.exception")


def _resolve_error_code(error: DomainError) -> tuple[ErrorCode, str | None]:
    if isinstance(error, UserNotFoundError):
        return ErrorCode.NOT_FOUND_ERROR, None
    if isinstance(error, UsernameAlreadyExistsError):
        return ErrorCode.CREATED_ERROR, None
    if isinstance(error, InvalidUserUpdateError):
        return ErrorCode.PARAMETER_ERROR, str(error)
    return ErrorCode.REQUEST_ERROR, None


def to_error_response(error: DomainError) -> tuple[JsonResponse, int]:
    code, message = _resolve_error_code(error)
    logger.warning(
        "domain error",
        extra={"error_type": type(error).__name__, "detail": str(error), "error_code": code.full_code()},
    )
    response = JsonResponse.error(code=code, message=message)
    return response, code.status_code

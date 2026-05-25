from app.domain.user.exceptions import DomainError, InvalidUserUpdateError, UsernameAlreadyExistsError, UserNotFoundError
from app.interfaces.http.support.response.code.error_code import ErrorCode
from app.interfaces.http.support.response.json import JsonResponse


def to_error_response(error: DomainError) -> JsonResponse:
    if isinstance(error, UserNotFoundError):
        return JsonResponse.error(code=ErrorCode.NOT_FOUND_ERROR)
    if isinstance(error, UsernameAlreadyExistsError):
        return JsonResponse.error(code=ErrorCode.CREATED_ERROR)
    if isinstance(error, InvalidUserUpdateError):
        return JsonResponse.error(code=ErrorCode.PARAMETER_ERROR, message=str(error))
    return JsonResponse.error(code=ErrorCode.REQUEST_ERROR)

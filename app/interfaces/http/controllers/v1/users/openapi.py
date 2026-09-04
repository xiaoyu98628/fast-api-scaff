from typing import Any

from app.interfaces.http.exceptions.openapi import ValidationErrorDetail
from app.interfaces.http.shared.response.json import JsonResponse

USER_VALIDATION_ERROR_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[list[ValidationErrorDetail]],
    "description": "请求参数或用户资料不合法",
}

USER_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[None],
    "description": "用户不存在或已被删除",
}

USER_CONFLICT_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[None],
    "description": "用户名或邮箱已存在",
}

"""声明认证端点在 OpenAPI 中复用的错误响应。"""

from typing import Any

from app.interfaces.http.exceptions.openapi import ValidationErrorDetail
from app.interfaces.http.shared.response.json import JsonResponse

AUTH_REQUIRED_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[None],
    "description": "登录失败、凭据缺失或会话当前不可用",
    "headers": {"WWW-Authenticate": {"schema": {"type": "string"}, "description": "Bearer"}},
}

AUTH_VALIDATION_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[list[ValidationErrorDetail]],
    "description": "登录请求字段不合法",
}

AUTH_USER_NOT_FOUND_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[None],
    "description": "登录用户不存在",
}

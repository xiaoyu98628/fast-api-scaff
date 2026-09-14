"""声明认证端点在 OpenAPI 中复用的错误响应。"""

from typing import Any

from app.interfaces.http.controllers.v1.auth.schemas import LoginFailureDetail, LoginLockDetail
from app.interfaces.http.exceptions.openapi import ValidationErrorDetail
from app.interfaces.http.shared.response.json import JsonResponse

AUTH_REQUIRED_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[None],
    "description": "凭据缺失或会话当前不可用",
    "headers": {"WWW-Authenticate": {"schema": {"type": "string"}, "description": "Bearer"}},
}

LOGIN_INVALID_CREDENTIALS_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[LoginFailureDetail],
    "description": "用户名或密码错误；启用登录限制时返回剩余尝试次数",
    "headers": {"WWW-Authenticate": {"schema": {"type": "string"}, "description": "Bearer"}},
}

AUTH_RATE_LIMIT_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[LoginLockDetail],
    "description": "同一用户名失败次数达到阈值，登录暂时锁定",
    "headers": {
        "Retry-After": {"schema": {"type": "integer"}, "description": "再次尝试前等待的秒数"},
        "Cache-Control": {"schema": {"type": "string"}, "description": "no-store"},
    },
}

AUTH_VALIDATION_RESPONSE: dict[str, Any] = {
    "model": JsonResponse[list[ValidationErrorDetail]],
    "description": "登录请求字段不合法",
}

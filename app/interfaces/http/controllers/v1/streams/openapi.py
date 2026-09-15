"""声明事件流端点的 JSON 校验错误响应文档。"""

from typing import Any

from app.interfaces.http.exceptions.openapi import ValidationErrorDetail

# SSE 路由显式声明 JSON 媒体类型，避免附加 model 沿用 text/event-stream。
STREAM_VALIDATION_ERROR_RESPONSE: dict[str, Any] = {
    "description": "事件流查询参数不合法，响应开始前返回统一 JSON 错误",
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["code", "success", "message"],
                "properties": {
                    "code": {"type": "string"},
                    "success": {"type": "boolean"},
                    "message": {"type": "string"},
                    "data": {
                        "anyOf": [
                            {"type": "array", "items": ValidationErrorDetail.model_json_schema(mode="serialization")},
                            {"type": "null"},
                        ],
                        "default": None,
                    },
                    "request_id": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                },
            },
        },
    },
}

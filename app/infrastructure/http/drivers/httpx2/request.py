from typing import Any

import httpx2

from app.infrastructure.http.contracts.request import HTTP_UNSET, HttpRequest


def build_httpx2_request_arguments(request: HttpRequest) -> dict[str, Any]:
    """将公共请求契约转换为普通和流式调用共用的 HTTPX2 参数。"""
    arguments: dict[str, Any] = {
        "method": request.method,
        "url": request.url,
        "headers": request.headers,
        "params": request.params,
    }
    if request.content is not None:
        arguments["content"] = request.content
    if request.json is None:
        headers = httpx2.Headers(request.headers)
        if "content-type" not in headers:
            headers["content-type"] = "application/json"
        arguments["headers"] = headers
        arguments["content"] = b"null"
    elif request.json is not HTTP_UNSET:
        arguments["json"] = request.json
    if request.timeout is not None:
        arguments["timeout"] = request.timeout

    return arguments

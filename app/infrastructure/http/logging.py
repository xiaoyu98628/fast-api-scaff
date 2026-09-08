"""构造不包含请求敏感数据的 HTTP 出站结构化日志。"""

import logging
from enum import StrEnum
from urllib.parse import urlsplit

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.logging.record import log_extra

HTTP_LOGGER = logging.getLogger("app.infrastructure.http")


class HttpLogEvent(StrEnum):
    """HTTP 出站资源、请求、流和连接池使用的稳定事件名。"""

    REQUEST_COMPLETED = "http.outbound.request.completed"
    REQUEST_FAILED = "http.outbound.request.failed"
    REQUEST_CANCELLED = "http.outbound.request.cancelled"
    STREAM_CONNECTED = "http.outbound.stream.connected"
    STREAM_COMPLETED = "http.outbound.stream.completed"
    STREAM_FAILED = "http.outbound.stream.failed"
    STREAM_CANCELLED = "http.outbound.stream.cancelled"
    POOL_PRESSURE = "http.outbound.pool.pressure"
    POOL_TIMEOUT = "http.outbound.pool.timeout"
    RESOURCE_CREATED = "http.outbound.resource.created"
    RESOURCE_CLOSED = "http.outbound.resource.closed"


def request_log_details(request: HttpRequest, **details: object) -> dict[str, object]:
    """只提取 method、origin 和调用方提供的低基数 operation。"""

    # 不记录 path、query、headers 或 body，避免凭据和业务数据进入日志。
    values: dict[str, object] = {
        "method": request.method,
        "origin": _safe_origin(request.url),
    }
    if request.operation is not None:
        values["operation"] = request.operation

    values.update(details)
    return values


def write_http_log(
    level: int,
    event: HttpLogEvent,
    message: str,
    request: HttpRequest,
    **details: object,
) -> None:
    """把安全请求摘要与调用阶段详情写入统一日志。"""

    HTTP_LOGGER.log(level, message, extra=log_extra(event, **request_log_details(request, **details)))


def _safe_origin(url: str) -> str:
    """只渲染 scheme、hostname 和显式端口，隐藏其他 URL 内容。"""

    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
        port = parsed_url.port
    except ValueError:
        return "<invalid>"

    if hostname is None or parsed_url.scheme not in {"http", "https"}:
        return "<invalid>"

    rendered_hostname = f"[{hostname}]" if ":" in hostname else hostname
    origin = f"{parsed_url.scheme}://{rendered_hostname}"
    return f"{origin}:{port}" if port is not None else origin

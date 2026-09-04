import logging
from enum import StrEnum
from urllib.parse import urlsplit

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.logging.record import log_extra

HTTP_LOGGER = logging.getLogger("app.infrastructure.http")


class HttpLogEvent(StrEnum):
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
    HTTP_LOGGER.log(level, message, extra=log_extra(event, **request_log_details(request, **details)))


def _safe_origin(url: str) -> str:
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

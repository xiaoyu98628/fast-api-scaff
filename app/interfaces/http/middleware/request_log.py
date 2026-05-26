"""请求访问日志：每个 HTTP 请求两条（request / response）→ ``request.log``。"""

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response, StreamingResponse

from app.infrastructure.context.request_scope import get_trace_id
from config.config import config

SENSITIVE_KEYS = frozenset({"password", "token", "access_token", "refresh_token", "authorization"})
_SKIP_PATHS = frozenset({"/health", "/favicon.ico"})
_LOG_PAYLOAD_MAX_LEN = 8000

logger = logging.getLogger("app.request")


def _payload_for_log(obj: Any, *, max_len: int = _LOG_PAYLOAD_MAX_LEN) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        text = str(obj)
    if len(text) > max_len:
        return f"{text[: max_len - 20]}...<truncated len={len(text)}>"
    return text


def _mask_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else _mask_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_mask_payload(item) for item in payload]
    return payload


def _parse_body_bytes(body: bytes, content_type: str) -> Any | None:
    if not body:
        return None
    if "application/json" in content_type:
        try:
            return _mask_payload(json.loads(body))
        except json.JSONDecodeError:
            return body.decode("utf-8", errors="ignore")[:500]
    return body.decode("utf-8", errors="ignore")[:500]


async def _extract_request_params(request: Request) -> dict[str, Any]:
    params: dict[str, Any] = {"query": dict(request.query_params.multi_items())}

    try:
        body = await request.body()
    except ClientDisconnect:
        params["error"] = "client_disconnected_before_body_read"
        return params
    except Exception as exc:
        params["error"] = f"body_read_error: {exc}"
        return params

    parsed = _parse_body_bytes(body, request.headers.get("content-type", ""))
    if parsed is not None:
        params["body"] = parsed
    return params


async def _capture_response(response: Response) -> tuple[Any | None, Response]:
    if isinstance(response, StreamingResponse):
        return {"_note": "streaming_response"}, response

    body = b"".join([chunk async for chunk in response.body_iterator])
    parsed = _parse_body_bytes(body, response.headers.get("content-type", ""))
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        headers=response.headers,
        media_type=response.media_type,
        background=response.background,
    )
    return parsed, rebuilt


def _log_request(
    *,
    json_enabled: bool,
    method: str,
    path: str,
    query: str | None,
    client_ip: str,
    trace_id: str,
    params: dict[str, Any],
) -> None:
    extra = {
        "event": "http.request",
        "direction": "in",
        "method": method,
        "path": path,
        "query": query,
        "client_ip": client_ip,
        "trace_id": trace_id,
        "params": params,
    }
    if json_enabled:
        logger.info("--> %s %s | ip=%s", method, path, client_ip, extra=extra)
        return

    message = f'--> {client_ip} "{method} {path}" trace_id={trace_id} params={_payload_for_log(params)}'
    if query:
        message = f'{message} query="{query}"'
    logger.info(message)


def _log_response(
    *,
    json_enabled: bool,
    method: str,
    path: str,
    client_ip: str,
    trace_id: str,
    status_code: int,
    duration_ms: float,
    response_body: Any | None,
) -> None:
    extra = {
        "event": "http.response",
        "direction": "out",
        "method": method,
        "path": path,
        "client_ip": client_ip,
        "trace_id": trace_id,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "response": response_body,
    }
    if json_enabled:
        logger.info(
            "<-- %s %s -> %s (%.2f ms) | ip=%s",
            method,
            path,
            status_code,
            duration_ms,
            client_ip,
            extra=extra,
        )
        return

    logger.info(
        f' <-- {client_ip} "{method} {path}" {status_code} {duration_ms}ms '
        f"trace_id={trace_id} response={_payload_for_log(response_body)}"
    )


class RequestLogMiddleware(BaseHTTPMiddleware):
    """每个请求写两条访问日志：进站 request、出站 response。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        started = time.perf_counter()
        json_enabled = config().logging.json_enabled
        client_ip = request.client.host if request.client else "-"
        trace_id = get_trace_id()
        query = request.url.query or None
        params = await _extract_request_params(request)

        _log_request(
            json_enabled=json_enabled,
            method=request.method,
            path=request.url.path,
            query=query,
            client_ip=client_ip,
            trace_id=trace_id,
            params=params,
        )

        status_code = 500
        response_body: Any | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response_body, response = await _capture_response(response)
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _log_response(
                json_enabled=json_enabled,
                method=request.method,
                path=request.url.path,
                client_ip=client_ip,
                trace_id=trace_id,
                status_code=status_code,
                duration_ms=duration_ms,
                response_body=response_body,
            )

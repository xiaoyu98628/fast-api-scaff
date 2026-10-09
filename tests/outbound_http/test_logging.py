"""验证出站 HTTP 请求、流和连接池结构化日志。"""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import httpx2
import pytest

from app.infrastructure.http.clients.managed import ManagedHttpClient
from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.drivers.httpx2.resource import Httpx2Resource
from app.infrastructure.http.errors import HttpTransportError
from app.infrastructure.http.logging import HttpLogEvent, request_log_details


class FakeStreamResponse:
    status_code = 200
    headers: tuple[tuple[str, str], ...] = ()

    async def aread(self) -> bytes:
        return b"stream"

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield b"stream"

    async def aiter_text(self) -> AsyncIterator[str]:
        yield "stream"


class FakeDriver:
    async def request(self, request: HttpRequest) -> HttpResponse:
        del request
        return HttpResponse(status_code=200, headers=(), content=b"ok")

    @asynccontextmanager
    async def stream(self, request: HttpRequest) -> AsyncIterator[FakeStreamResponse]:
        del request
        yield FakeStreamResponse()

    async def aclose(self) -> None:
        return None


class BlockingDriver(FakeDriver):
    async def request(self, request: HttpRequest) -> HttpResponse:
        del request
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_request_log_includes_route_and_excludes_other_request_data(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())

    with capture_http_logs(caplog):
        await client.request(
            HttpRequest(
                method="POST",
                url="https://url-user-secret:url-password-secret@example.com/users/user-id?token=query-secret#fragment-secret",
                headers={"Authorization": "Bearer header-secret"},
                params={"extra": "params-secret"},
                content=b"body-secret",
                operation="users.get",
            )
        )

    record = caplog.records[-1]
    rendered = f"{record.getMessage()} {getattr(record, 'details', {})}"
    for secret in ("header-secret", "query-secret", "fragment-secret", "params-secret", "body-secret", "url-user-secret", "url-password-secret"):
        assert secret not in rendered
    details = getattr(record, "details")
    assert details["method"] == "POST"
    assert details["origin"] == "https://example.com"
    assert details["route"] == "/users/user-id"
    assert details["operation"] == "users.get"


@pytest.mark.asyncio
async def test_stream_logs_include_route_without_credentials_or_request_data(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())
    request = HttpRequest(
        method="POST",
        url="https://url-user-secret:url-password-secret@example.com/events?token=query-secret#fragment-secret",
        headers={"Authorization": "Bearer header-secret"},
        content=b"body-secret",
    )
    with capture_http_logs(caplog):
        async with client.stream(request) as response:
            assert await response.aread() == b"stream"

    assert _events(caplog) == {HttpLogEvent.STREAM_CONNECTED, HttpLogEvent.STREAM_COMPLETED}
    for record in caplog.records:
        details = getattr(record, "details")
        assert details["route"] == "/events"
        assert details["origin"] == "https://example.com"
        rendered = f"{record.getMessage()} {details}"
        for secret in ("url-user-secret", "url-password-secret", "header-secret", "body-secret", "query-secret", "fragment-secret"):
            assert secret not in rendered


@pytest.mark.parametrize(
    ("url", "origin", "route"),
    [
        ("https://example.com", "https://example.com", "/"),
        ("https://example.com?token=secret#ignored", "https://example.com", "/"),
        ("https://user:password@example.com:8443/Users/u-1?token=secret#ignored", "https://example.com:8443", "/Users/u-1"),
        ("https://example.com/users/a%2Fb?token=secret", "https://example.com", "/users/a%2Fb"),
    ],
)
def test_request_log_preserves_raw_route_and_omits_other_url_components(url: str, origin: str, route: str) -> None:
    assert request_log_details(HttpRequest(method="GET", url=url)) == {"method": "GET", "origin": origin, "route": route}


def test_request_log_origin_formats_ipv6_and_degrades_on_invalid_url() -> None:
    request = HttpRequest(method="GET", url="https://[2001:db8::1]:8443/private")

    details = request_log_details(request)
    assert details["origin"] == "https://[2001:db8::1]:8443"
    assert details["route"] == "/private"

    object.__setattr__(request, "url", "https://example.com:notaport/private")

    details = request_log_details(request)
    assert details["origin"] == "<invalid>"
    assert details["route"] == "<invalid>"


@pytest.mark.parametrize("invalid_url", ["/relative/private", "ftp://example.com/private", "https://[invalid-host/private"])
def test_request_log_handles_unexpected_invalid_url(invalid_url: str) -> None:
    request = HttpRequest(method="GET", url="https://example.com/private")
    # 正常构造会拒绝这些地址，这里模拟被破坏的请求，检查诊断逻辑不掩盖原始故障。
    object.__setattr__(request, "url", invalid_url)

    assert request_log_details(request) == {"method": "GET", "origin": "<invalid>", "route": "<invalid>"}


@pytest.mark.asyncio
async def test_cancelled_request_is_not_logged_as_failure(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(BlockingDriver())
    request = HttpRequest(method="GET", url="https://example.com/slow")

    with capture_http_logs(caplog):
        task = asyncio.create_task(client.request(request))
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    assert HttpLogEvent.REQUEST_FAILED not in _events(caplog)
    assert HttpLogEvent.REQUEST_CANCELLED in _events(caplog)
    cancelled = next(record for record in caplog.records if getattr(record, "event", None) == HttpLogEvent.REQUEST_CANCELLED)
    assert getattr(cancelled, "details")["route"] == "/slow"


@pytest.mark.asyncio
async def test_cancelled_stream_is_not_logged_as_failure(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())
    request = HttpRequest(method="GET", url="https://example.com/events")

    async def consume() -> None:
        async with client.stream(request):
            await asyncio.Event().wait()

    with capture_http_logs(caplog):
        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    assert HttpLogEvent.STREAM_FAILED not in _events(caplog)
    assert HttpLogEvent.STREAM_CANCELLED in _events(caplog)
    cancelled = next(record for record in caplog.records if getattr(record, "event", None) == HttpLogEvent.STREAM_CANCELLED)
    assert getattr(cancelled, "details")["route"] == "/events"


@pytest.mark.asyncio
async def test_caller_error_is_not_logged_as_stream_failure(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())
    request = HttpRequest(method="GET", url="https://example.com/events")

    with capture_http_logs(caplog), pytest.raises(RuntimeError, match="consumer failed"):
        async with client.stream(request):
            raise RuntimeError("consumer failed")

    assert HttpLogEvent.STREAM_FAILED not in _events(caplog)


@pytest.mark.asyncio
async def test_transport_error_is_logged_as_stream_failure(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())
    request = HttpRequest(method="GET", url="https://example.com/events")

    with capture_http_logs(caplog), pytest.raises(HttpTransportError, match="stream failed"):
        async with client.stream(request):
            raise HttpTransportError("stream failed")

    assert HttpLogEvent.STREAM_FAILED in _events(caplog)


@pytest.mark.asyncio
async def test_pool_timeout_has_dedicated_event(caplog: pytest.LogCaptureFixture) -> None:
    async def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.PoolTimeout("pool exhausted", request=request)

    resource = Httpx2Resource(
        standard_client=httpx2.AsyncClient(transport=httpx2.MockTransport(fail)),
        stream_client=httpx2.AsyncClient(transport=httpx2.MockTransport(fail)),
        standard_pool_limit=1,
        pool_warning_ratio=1.0,
    )

    try:
        with capture_http_logs(caplog), pytest.raises(HttpTransportError):
            await resource.request(HttpRequest(method="GET", url="https://example.com/busy"))
    finally:
        await resource.aclose()

    assert HttpLogEvent.POOL_TIMEOUT in _events(caplog)
    assert HttpLogEvent.POOL_PRESSURE in _events(caplog)

    timeout_record = next(record for record in caplog.records if getattr(record, "event", None) == HttpLogEvent.POOL_TIMEOUT)
    details = getattr(timeout_record, "details")
    assert details["pool"] == "standard"
    assert details["active"] == 1
    assert details["peak_active"] == 1
    assert details["limit"] == 1
    assert details["pool_timeout"] == 1
    assert details["client_id"].startswith("0x")
    assert "pool_id" not in details
    assert "pool_state" not in details


@contextmanager
def capture_http_logs(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    logger = logging.getLogger("app.infrastructure.http")
    previous_disabled = logger.disabled
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(caplog.handler)

    try:
        yield
    finally:
        logger.removeHandler(caplog.handler)
        logger.disabled = previous_disabled
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def _events(caplog: pytest.LogCaptureFixture) -> set[HttpLogEvent | str]:
    return {event for record in caplog.records if (event := getattr(record, "event", None)) is not None}

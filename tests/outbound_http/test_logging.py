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
async def test_request_log_does_not_include_headers_query_or_path(caplog: pytest.LogCaptureFixture) -> None:
    client = ManagedHttpClient(FakeDriver())

    with capture_http_logs(caplog):
        await client.request(
            HttpRequest(
                method="GET",
                url="https://example.com/users/private-id?token=query-secret",
                headers={"Authorization": "Bearer header-secret"},
                operation="users.get",
            )
        )

    record = caplog.records[-1]
    rendered = f"{record.getMessage()} {getattr(record, 'details', {})}"
    assert "header-secret" not in rendered
    assert "query-secret" not in rendered
    assert "private-id" not in rendered
    assert getattr(record, "details")["origin"] == "https://example.com"


def test_request_log_origin_formats_ipv6_and_degrades_on_invalid_url() -> None:
    request = HttpRequest(method="GET", url="https://[2001:db8::1]:8443/private")

    assert request_log_details(request)["origin"] == "https://[2001:db8::1]:8443"

    object.__setattr__(request, "url", "https://example.com:notaport/private")

    assert request_log_details(request)["origin"] == "<invalid>"


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

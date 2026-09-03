from collections.abc import Callable, Coroutine

import httpx2
import pytest

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.drivers.httpx2.resource import Httpx2Resource
from app.infrastructure.http.errors import HttpResponseTooLargeError, HttpTimeoutError


@pytest.mark.asyncio
async def test_regular_request_returns_driver_independent_buffered_response() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers=[("set-cookie", "a=1"), ("set-cookie", "b=2")], json={"ok": True})

    resource = _resource(handler)

    try:
        response = await resource.request(HttpRequest(method="get", url="https://example.com/items"))
    finally:
        await resource.aclose()

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.header_values("set-cookie") == ("a=1", "b=2")
    assert resource.standard_runtime.active == 0


@pytest.mark.asyncio
async def test_httpx2_timeout_is_translated() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    resource = _resource(handler)

    try:
        with pytest.raises(HttpTimeoutError, match="超时"):
            await resource.request(HttpRequest(method="GET", url="https://example.com/slow"))
    finally:
        await resource.aclose()


@pytest.mark.asyncio
async def test_explicit_json_null_is_distinct_from_missing_json() -> None:
    received: list[tuple[bytes, str | None]] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        received.append((request.content, request.headers.get("content-type")))
        return httpx2.Response(204)

    resource = _resource(handler)

    try:
        await resource.request(HttpRequest(method="POST", url="https://example.com/missing"))
        await resource.request(HttpRequest(method="POST", url="https://example.com/null", json=None))
    finally:
        await resource.aclose()

    assert received == [
        (b"", None),
        (b"null", "application/json"),
    ]


@pytest.mark.asyncio
async def test_regular_request_rejects_response_larger_than_buffer_limit() -> None:
    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"too-large")

    transport = httpx2.MockTransport(handler)
    resource = Httpx2Resource(
        standard_client=httpx2.AsyncClient(transport=transport),
        stream_client=httpx2.AsyncClient(transport=transport),
        max_response_bytes=4,
    )

    try:
        with pytest.raises(HttpResponseTooLargeError) as captured_error:
            await resource.request(HttpRequest(method="GET", url="https://example.com/large"))
    finally:
        await resource.aclose()

    assert captured_error.value.max_response_bytes == 4
    assert resource.standard_runtime.active == 0


@pytest.mark.parametrize(
    "request_factory",
    [
        pytest.param(lambda: HttpRequest(method="", url="https://example.com"), id="empty-method"),
        pytest.param(lambda: HttpRequest(method="GET", url="/relative"), id="relative-url"),
        pytest.param(lambda: HttpRequest(method="GET", url="https://example.com:notaport"), id="invalid-port"),
        pytest.param(lambda: HttpRequest(method="GET", url="https://example.com:65536"), id="out-of-range-port"),
        pytest.param(
            lambda: HttpRequest(method="POST", url="https://example.com", content=b"x", json={}),
            id="multiple-bodies",
        ),
    ],
)
def test_request_rejects_invalid_transport_input(request_factory: Callable[[], HttpRequest]) -> None:
    with pytest.raises(ValueError):
        request_factory()


def _resource(handler: Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]]) -> Httpx2Resource:
    transport = httpx2.MockTransport(handler)
    return Httpx2Resource(
        standard_client=httpx2.AsyncClient(transport=transport),
        stream_client=httpx2.AsyncClient(transport=transport),
    )

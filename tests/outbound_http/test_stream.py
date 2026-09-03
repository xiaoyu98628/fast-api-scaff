import httpx2
import pytest

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.drivers.httpx2.resource import Httpx2Resource


@pytest.mark.asyncio
async def test_stream_uses_independent_client_and_returns_chunks() -> None:
    calls: list[str] = []

    async def standard_handler(_request: httpx2.Request) -> httpx2.Response:
        calls.append("standard")
        return httpx2.Response(200, content=b"standard")

    async def stream_handler(_request: httpx2.Request) -> httpx2.Response:
        calls.append("stream")
        return httpx2.Response(200, content=b"first-second")

    resource = Httpx2Resource(
        standard_client=httpx2.AsyncClient(transport=httpx2.MockTransport(standard_handler)),
        stream_client=httpx2.AsyncClient(transport=httpx2.MockTransport(stream_handler)),
    )

    try:
        regular = await resource.request(HttpRequest(method="GET", url="https://example.com/regular"))
        async with resource.stream(HttpRequest(method="GET", url="https://example.com/stream")) as response:
            chunks = [chunk async for chunk in response.aiter_bytes()]
    finally:
        await resource.aclose()

    assert regular.content == b"standard"
    assert b"".join(chunks) == b"first-second"
    assert calls == ["standard", "stream"]
    assert resource.stream_runtime.active == 0


@pytest.mark.asyncio
async def test_stream_distinguishes_missing_json_from_explicit_null() -> None:
    received: list[tuple[bytes, str | None]] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        received.append((request.content, request.headers.get("content-type")))
        return httpx2.Response(204)

    transport = httpx2.MockTransport(handler)
    resource = Httpx2Resource(
        standard_client=httpx2.AsyncClient(transport=transport),
        stream_client=httpx2.AsyncClient(transport=transport),
    )

    try:
        async with resource.stream(HttpRequest(method="POST", url="https://example.com/missing")):
            pass
        async with resource.stream(HttpRequest(method="POST", url="https://example.com/null", json=None)):
            pass
    finally:
        await resource.aclose()

    assert received == [
        (b"", None),
        (b"null", "application/json"),
    ]

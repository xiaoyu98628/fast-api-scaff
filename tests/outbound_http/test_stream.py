import httpx
import pytest

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.drivers.httpx.resource import HttpxResource


@pytest.mark.asyncio
async def test_stream_uses_independent_client_and_returns_chunks() -> None:
    calls: list[str] = []

    async def standard_handler(_request: httpx.Request) -> httpx.Response:
        calls.append("standard")
        return httpx.Response(200, content=b"standard")

    async def stream_handler(_request: httpx.Request) -> httpx.Response:
        calls.append("stream")
        return httpx.Response(200, content=b"first-second")

    resource = HttpxResource(
        standard_client=httpx.AsyncClient(transport=httpx.MockTransport(standard_handler)),
        stream_client=httpx.AsyncClient(transport=httpx.MockTransport(stream_handler)),
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

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append((request.content, request.headers.get("content-type")))
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    resource = HttpxResource(
        standard_client=httpx.AsyncClient(transport=transport),
        stream_client=httpx.AsyncClient(transport=transport),
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

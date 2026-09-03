from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

import app.infrastructure.http.manager as manager_module
from app.config.http import HttpSettings
from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.contracts.response import HttpResponse
from app.infrastructure.http.manager import HttpClientManager


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
    def __init__(self) -> None:
        self.closed = False

    async def request(self, _request: HttpRequest) -> HttpResponse:
        return HttpResponse(status_code=200, headers=(), content=b"ok")

    @asynccontextmanager
    async def stream(self, _request: HttpRequest) -> AsyncIterator[FakeStreamResponse]:
        yield FakeStreamResponse()

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_manager_lazily_reuses_and_closes_single_global_client(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver()
    monkeypatch.setattr(manager_module, "create_httpx2_resource", lambda _settings: driver)
    manager = HttpClientManager(HttpSettings(_env_file=None))

    assert manager.is_initialized is False
    first = await manager.get()
    second = await manager.get()
    response = await manager.request(HttpRequest(method="GET", url="https://example.com"))

    async with manager.stream(HttpRequest(method="GET", url="https://example.com/events")) as stream:
        stream_content = await stream.aread()

    assert first is second
    assert response.content == b"ok"
    assert stream_content == b"stream"
    assert manager.is_initialized is True

    await manager.aclose()

    assert driver.closed is True
    assert manager.is_initialized is False

    with pytest.raises(RuntimeError, match="已经关闭"):
        await manager.get()

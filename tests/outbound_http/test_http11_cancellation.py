import asyncio

import httpx
import pytest

from app.infrastructure.http.contracts.request import HttpRequest
from app.infrastructure.http.drivers.httpx.resource import HttpxResource


@pytest.mark.asyncio
async def test_cancelled_http11_stream_does_not_exhaust_single_connection_pool() -> None:
    writers: set[asyncio.StreamWriter] = set()
    server = await asyncio.start_server(
        lambda reader, writer: _serve_stream(reader, writer, writers),
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    timeout = httpx.Timeout(connect=1.0, read=None, write=1.0, pool=0.5)
    resource = HttpxResource(
        standard_client=httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False),
        stream_client=httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False),
    )
    request = HttpRequest(method="GET", url=f"http://127.0.0.1:{port}/events")
    received = asyncio.Event()

    async def consume_until_cancelled() -> None:
        async with resource.stream(request) as response:
            async for _chunk in response.aiter_bytes():
                received.set()
                await asyncio.Event().wait()

    task = asyncio.create_task(consume_until_cancelled())

    try:
        await asyncio.wait_for(received.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        async with resource.stream(request) as response:
            chunk = await asyncio.wait_for(anext(response.aiter_bytes()), timeout=2.0)

        assert chunk == b"data\n"
    finally:
        if not task.done():
            task.cancel()
        await resource.aclose()
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()


async def _serve_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    writers: set[asyncio.StreamWriter],
) -> None:
    writers.add(writer)

    try:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\nConnection: keep-alive\r\n\r\n")
        await writer.drain()

        while True:
            writer.write(b"5\r\ndata\n\r\n")
            await writer.drain()
            await asyncio.sleep(0.02)
    except asyncio.IncompleteReadError, ConnectionError:
        pass
    finally:
        writers.discard(writer)
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


@pytest.mark.asyncio
async def test_cancelled_buffered_http11_request_does_not_exhaust_single_connection_pool() -> None:
    writers: set[asyncio.StreamWriter] = set()
    slow_response_started = asyncio.Event()
    server = await asyncio.start_server(
        lambda reader, writer: _serve_buffered_request(reader, writer, writers, slow_response_started),
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    timeout = httpx.Timeout(connect=1.0, read=None, write=1.0, pool=0.5)
    resource = HttpxResource(
        standard_client=httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False),
        stream_client=httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False),
    )
    slow_request = HttpRequest(method="GET", url=f"http://127.0.0.1:{port}/slow")
    fast_request = HttpRequest(method="GET", url=f"http://127.0.0.1:{port}/fast")
    task = asyncio.create_task(resource.request(slow_request))

    try:
        await asyncio.wait_for(slow_response_started.wait(), timeout=2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        response = await asyncio.wait_for(resource.request(fast_request), timeout=2.0)

        assert response.content == b"ok"
    finally:
        if not task.done():
            task.cancel()
        await resource.aclose()
        server.close()
        await server.wait_closed()
        for writer in tuple(writers):
            writer.close()


async def _serve_buffered_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    writers: set[asyncio.StreamWriter],
    slow_response_started: asyncio.Event,
) -> None:
    writers.add(writer)

    try:
        request = await reader.readuntil(b"\r\n\r\n")
        if request.startswith(b"GET /slow "):
            writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: keep-alive\r\n\r\n")
            writer.write(b"5\r\ndata\n\r\n")
            await writer.drain()
            slow_response_started.set()
            await reader.read()
        else:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
    except asyncio.IncompleteReadError, ConnectionError:
        pass
    finally:
        writers.discard(writer)
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass

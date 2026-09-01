from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from app.infrastructure.http.drivers.httpx.pool import HttpxPoolCompatibility


class FakeConnection:
    def __init__(self, *, idle: bool) -> None:
        self._idle = idle
        self.closed = False

    def is_idle(self) -> bool:
        return self._idle

    async def aclose(self) -> None:
        self.closed = True


class FakeLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class FakePool:
    def __init__(self, connections: list[FakeConnection], requests: list[object]) -> None:
        self._connections = connections
        self._requests = requests
        self._optional_thread_lock = FakeLock()

    def _assign_requests_to_connections(self) -> list[FakeConnection]:
        return []

    async def _close_connections(self, connections: list[FakeConnection]) -> None:
        for connection in connections:
            await connection.aclose()


class FakeClient:
    def __init__(self, pool: FakePool) -> None:
        self._transport = SimpleNamespace(_pool=pool)

    def _transport_for_url(self, _url: object) -> object:
        return self._transport


@pytest.mark.asyncio
async def test_only_unreferenced_non_idle_connections_are_discarded() -> None:
    assigned = FakeConnection(idle=False)
    orphaned = FakeConnection(idle=False)
    idle = FakeConnection(idle=True)
    request = SimpleNamespace(connection=assigned)
    pool = FakePool([assigned, orphaned, idle], [request])
    compatibility = HttpxPoolCompatibility()

    client = cast(httpx.AsyncClient, FakeClient(pool))
    discarded = await compatibility.discard_orphaned_connections(client, "https://example.com")
    await compatibility.wait_for_cleanup()

    assert discarded == 1
    assert pool._connections == [assigned, idle]
    assert orphaned.closed is True
    assert assigned.closed is False
    assert idle.closed is False


@pytest.mark.asyncio
async def test_missing_private_pool_members_degrade_safely() -> None:
    client: Any = SimpleNamespace(_transport_for_url=lambda _url: object())
    compatibility = HttpxPoolCompatibility()

    assert await compatibility.discard_orphaned_connections(client, "https://example.com") == 0

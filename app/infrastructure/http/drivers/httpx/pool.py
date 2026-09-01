import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.infrastructure.http.logging import HTTP_LOGGER, HttpLogEvent
from app.infrastructure.logging.record import log_extra


@dataclass(slots=True)
class HttpPoolRuntime:
    """单个连接池的进程内诊断计数。"""

    active: int = 0
    peak_active: int = 0
    cancelled: int = 0
    pool_timeout: int = 0
    orphan_discarded: int = 0

    def acquire(self) -> None:
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)

    def release(self) -> None:
        self.active = max(0, self.active - 1)


class HttpxPoolCompatibility:
    """隔离 HTTPX 0.28.1/httpcore 1.0.9 私有连接池兼容逻辑。"""

    def __init__(self) -> None:
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._compatibility_warning_logged = False

    @property
    def cleanup_task_count(self) -> int:
        return len(self._cleanup_tasks)

    async def discard_orphaned_connections(self, client: httpx.AsyncClient, url: str) -> int:
        try:
            pool = self._resolve_pool(client, url)

            with pool._optional_thread_lock:
                referenced_connections = {request.connection for request in pool._requests if request.connection is not None}
                orphaned_connections = [
                    connection for connection in pool._connections if connection not in referenced_connections and not connection.is_idle()
                ]

                if not orphaned_connections:
                    return 0

                orphaned_ids = {id(connection) for connection in orphaned_connections}
                pool._connections = [connection for connection in pool._connections if id(connection) not in orphaned_ids]
                closing_connections = orphaned_connections + pool._assign_requests_to_connections()

            self._start_cleanup(pool, closing_connections)
            HTTP_LOGGER.warning(
                "Discarded orphaned outbound HTTP connections",
                extra=log_extra(
                    HttpLogEvent.POOL_ORPHAN_DISCARDED,
                    count=len(orphaned_connections),
                ),
            )
            return len(orphaned_connections)
        except AttributeError, TypeError:
            self._log_compatibility_warning()
            return 0

    async def wait_for_cleanup(self) -> None:
        if self._cleanup_tasks:
            await asyncio.gather(*tuple(self._cleanup_tasks), return_exceptions=True)

    @staticmethod
    def _resolve_pool(client: httpx.AsyncClient, url: str) -> Any:
        transport: Any = client._transport_for_url(httpx.URL(url))
        return transport._pool

    def _start_cleanup(self, pool: Any, connections: list[Any]) -> None:
        if not connections:
            return

        task = asyncio.create_task(pool._close_connections(connections))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_finished)

    def _cleanup_finished(self, task: asyncio.Task[None]) -> None:
        self._cleanup_tasks.discard(task)

        try:
            task.result()
        except asyncio.CancelledError:
            HTTP_LOGGER.warning(
                "Outbound HTTP orphan cleanup task was cancelled",
                extra=log_extra(HttpLogEvent.POOL_ORPHAN_CLOSE_FAILED, error_type="CancelledError"),
            )
        except Exception as error:
            HTTP_LOGGER.exception(
                "Failed to close orphaned outbound HTTP connections",
                extra=log_extra(HttpLogEvent.POOL_ORPHAN_CLOSE_FAILED, error_type=type(error).__name__),
            )

    def _log_compatibility_warning(self) -> None:
        if self._compatibility_warning_logged:
            return

        self._compatibility_warning_logged = True
        HTTP_LOGGER.log(
            logging.WARNING,
            "HTTPX/httpcore pool internals are not compatible with orphan cleanup",
            extra=log_extra(HttpLogEvent.POOL_COMPATIBILITY_FAILED),
        )

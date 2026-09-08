"""提供队列后端统一的异步资源关闭回调。"""

from app.infrastructure.queue.contracts.provider import QueueBackend


async def close_backend(backend: QueueBackend) -> None:
    """关闭一个由延迟资源持有的队列后端。"""

    await backend.aclose()

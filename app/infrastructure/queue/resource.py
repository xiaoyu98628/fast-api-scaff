from app.infrastructure.queue.contracts.provider import QueueBackend


async def close_backend(backend: QueueBackend) -> None:
    await backend.aclose()

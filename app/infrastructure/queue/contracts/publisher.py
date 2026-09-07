from typing import Protocol


class QueuePublisher(Protocol):
    async def publish(self, queue: str, payload: bytes) -> None: ...

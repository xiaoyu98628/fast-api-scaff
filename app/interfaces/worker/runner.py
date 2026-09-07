import asyncio
import math

from app.infrastructure.queue.contracts.consumer import QueueConsumer
from app.infrastructure.queue.errors import DeliveryLostError
from app.interfaces.worker.executor import JobExecutor


class WorkerRunner:
    def __init__(self, *, concurrency: int, shutdown_timeout: float) -> None:
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError("concurrency 必须为正整数")
        if not math.isfinite(shutdown_timeout) or shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout 必须为有限正数")
        self._concurrency = concurrency
        self._shutdown_timeout = shutdown_timeout
        self._receivers: set[asyncio.Task] = set()
        self._closing = False

    async def run(self, consumer: QueueConsumer, executor: JobExecutor, stop: asyncio.Event) -> None:
        self._closing = False
        tasks = [asyncio.create_task(self._lane(consumer, executor, stop)) for _ in range(self._concurrency)]
        stopped = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait([*tasks, stopped], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stopped:
                    await task
            self._closing = True
            for receiver in tuple(self._receivers):
                receiver.cancel()
            _, pending = await asyncio.wait(tasks, timeout=self._shutdown_timeout)
            for task in pending:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [result for result in results if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError)]
            if errors:
                raise BaseExceptionGroup("Worker 执行失败", errors)
        finally:
            self._closing = True
            stopped.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, stopped, return_exceptions=True)

    async def _lane(self, consumer: QueueConsumer, executor: JobExecutor, stop: asyncio.Event) -> None:
        task = asyncio.current_task()
        assert task is not None
        try:
            while not stop.is_set():
                self._receivers.add(task)
                try:
                    delivery = await consumer.receive()
                finally:
                    self._receivers.discard(task)
                await executor.execute(delivery)
        except asyncio.CancelledError:
            if not self._closing:
                raise DeliveryLostError("消费任务被取消，可能发生租约丢失或再均衡") from None
            raise

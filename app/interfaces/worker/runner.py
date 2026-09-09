"""管理 Worker 并发执行槽和停止时的任务排空。"""

import asyncio
import math

from app.infrastructure.queue.contracts.consumer import QueueConsumer
from app.infrastructure.queue.errors import DeliveryLostError
from app.interfaces.worker.executor import JobExecutor


class WorkerRunner:
    """以固定执行槽消费消息，并区分等待接收与在途执行。"""

    def __init__(self, *, concurrency: int, shutdown_timeout: float) -> None:
        """校验并保存执行槽数量和停止排空等待时间。"""

        if type(concurrency) is not int or concurrency < 1:
            raise ValueError("concurrency 必须为正整数")
        if not math.isfinite(shutdown_timeout) or shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout 必须为有限正数")
        self._concurrency = concurrency
        self._shutdown_timeout = shutdown_timeout
        self._receivers: set[asyncio.Task] = set()
        self._closing = False

    async def run(self, consumer: QueueConsumer, executor: JobExecutor, stop: asyncio.Event) -> None:
        """运行到停止信号或首个执行槽失败，然后有界等待在途任务。"""

        self._closing = False
        tasks = [asyncio.create_task(self._lane(consumer, executor, stop)) for _ in range(self._concurrency)]
        stopped = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait([*tasks, stopped], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stopped:
                    await task
            self._closing = True
            # 先取消仍在 receive() 中的槽，已经拿到 delivery 的槽继续排空。
            for receiver in tuple(self._receivers):
                receiver.cancel()
            _, pending = await asyncio.wait(tasks, timeout=self._shutdown_timeout)
            # 超过关闭上限后请求取消；无法强制终止不响应取消的业务代码。
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
        """串行执行单个消费槽，保证每个槽同一时刻只有一个 delivery。"""

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
            # 非正常关闭中的取消通常来自 Redis 租约丢失或 Kafka 再均衡。
            if not self._closing:
                raise DeliveryLostError("消费任务被取消，可能发生租约丢失或再均衡") from None
            raise

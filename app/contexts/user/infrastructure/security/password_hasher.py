"""使用 pwdlib 在线程池中实现密码哈希协议。"""

import asyncio
from collections.abc import Callable
from functools import partial

from anyio import CancelScope, CapacityLimiter, to_thread
from pwdlib import PasswordHash as PwdlibPasswordHash
from pwdlib.exceptions import UnknownHashError

from app.contexts.user.domain.values import Password, PasswordHash

_DUMMY_PASSWORD_HASH = PasswordHash("$argon2id$v=19$m=65536,t=3,p=4$02Keoy+DGPuHr5mUy59tsw$KlRhQ6wTlD0CHUm1FhjrgNWjseJuIFqTWejQfGj0C54")


class PwdlibPasswordHasher:
    """使用 pwdlib 推荐算法生成密码哈希。"""

    def __init__(self, *, max_concurrency: int = 2) -> None:
        """创建推荐算法实例并限制进程内密码计算并发量。"""

        self._hasher = PwdlibPasswordHash.recommended()
        self._limiter = CapacityLimiter(max_concurrency)

    async def hash(self, password: Password) -> PasswordHash:
        """在线程池中计算密码哈希，避免阻塞事件循环。"""

        return PasswordHash(await self._run(partial(self._hasher.hash, password.value)))

    async def verify_or_dummy(self, password: str, password_hash: PasswordHash | None) -> bool:
        """在线程池中校验密码，目标不存在时使用固定占位哈希。"""

        active_hash = _DUMMY_PASSWORD_HASH if password_hash is None else password_hash
        try:
            verified = await self._run(partial(self._hasher.verify, password, active_hash.value))
        except UnknownHashError:
            # pwdlib 的异常文本包含哈希，禁止它进入宿主日志。
            raise RuntimeError("存储的密码哈希无法识别") from None

        # 占位哈希永远不能成为一次成功认证，即使输入碰巧与其明文相同。
        return password_hash is not None and verified

    async def _run[T](self, operation: Callable[[], T]) -> T:
        """执行受并发限制的阻塞计算，并等待被取消任务真正结束。"""

        work = asyncio.create_task(to_thread.run_sync(operation, limiter=self._limiter))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            # Task.cancel() 也不能提前释放仍在执行的哈希所占用的额度。
            with CancelScope(shield=True):
                while not work.done():
                    try:
                        await asyncio.shield(work)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not work.cancelled():
                    work.exception()
            raise

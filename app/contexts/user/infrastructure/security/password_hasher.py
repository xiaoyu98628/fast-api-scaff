import asyncio
from collections.abc import Callable
from functools import partial

from anyio import CancelScope, CapacityLimiter, to_thread
from pwdlib import PasswordHash as PwdlibPasswordHash
from pwdlib.exceptions import UnknownHashError

from app.contexts.user.domain.values import Password, PasswordHash


class PwdlibPasswordHasher:
    """使用 pwdlib 推荐算法生成密码哈希。"""

    def __init__(self, *, max_concurrency: int = 2) -> None:
        self._hasher = PwdlibPasswordHash.recommended()
        self._limiter = CapacityLimiter(max_concurrency)

    async def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(await self._run(partial(self._hasher.hash, password.value)))

    async def verify(self, password: str, password_hash: PasswordHash) -> bool:
        try:
            return await self._run(partial(self._hasher.verify, password, password_hash.value))
        except UnknownHashError:
            # pwdlib 的异常文本包含哈希，禁止它进入宿主日志。
            raise RuntimeError("存储的密码哈希无法识别") from None

    async def _run[T](self, operation: Callable[[], T]) -> T:
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

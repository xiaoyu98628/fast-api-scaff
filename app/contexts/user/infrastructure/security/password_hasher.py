import asyncio

from anyio import CancelScope, CapacityLimiter, to_thread
from pwdlib import PasswordHash as PwdlibPasswordHash

from app.contexts.user.domain.values import Password, PasswordHash


class PwdlibPasswordHasher:
    """使用 pwdlib 推荐算法生成密码哈希。"""

    def __init__(self, *, max_concurrency: int = 2) -> None:
        self._hasher = PwdlibPasswordHash.recommended()
        self._limiter = CapacityLimiter(max_concurrency)

    async def hash(self, password: Password) -> PasswordHash:
        work = asyncio.create_task(to_thread.run_sync(self._hasher.hash, password.value, limiter=self._limiter))
        try:
            return PasswordHash(await asyncio.shield(work))
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

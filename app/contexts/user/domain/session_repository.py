from typing import Protocol

from app.contexts.user.domain.session import UserSession


class SessionRepository(Protocol):
    """与用户共享事务的会话持久化契约。"""

    async def find(self, token_digest: str) -> UserSession | None: ...

    async def add(self, session: UserSession) -> None: ...

    async def remove(self, token_digest: str) -> None:
        """幂等删除；不存在时也视为成功。"""
        ...

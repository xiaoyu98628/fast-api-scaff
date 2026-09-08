"""声明用户会话在 Domain 层需要的持久化能力。"""

from typing import Protocol

from app.contexts.user.domain.session import UserSession


class SessionRepository(Protocol):
    """与用户共享事务的会话持久化契约。"""

    async def find(self, token_digest: str) -> UserSession | None:
        """按令牌摘要查找服务器端会话。"""

        ...

    async def add(self, session: UserSession) -> None:
        """把新会话加入当前用户事务。"""

        ...

    async def remove(self, token_digest: str) -> None:
        """幂等删除；不存在时也视为成功。"""
        ...

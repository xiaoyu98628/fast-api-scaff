from typing import Protocol

from app.contexts.user.domain.values import Password, PasswordHash


class PasswordHasher(Protocol):
    """应用层所需的密码哈希能力。"""

    async def hash(self, password: Password) -> PasswordHash: ...

"""声明用户用例需要的密码哈希能力。"""

from typing import Protocol

from app.contexts.user.domain.values import Password, PasswordHash


class PasswordHasher(Protocol):
    """应用层所需的密码哈希能力。"""

    async def hash(self, password: Password) -> PasswordHash:
        """把已校验的明文密码转换为可持久化哈希。"""

        ...

    async def verify(self, password: str, password_hash: PasswordHash) -> bool:
        """验证原始密码是否匹配已有哈希。"""

        ...

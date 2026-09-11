"""声明用户用例需要的密码哈希能力。"""

from typing import Protocol

from app.contexts.user.domain.values import Password, PasswordHash


class PasswordHasher(Protocol):
    """应用层所需的密码哈希能力。"""

    async def hash(self, password: Password) -> PasswordHash:
        """把已校验的明文密码转换为可持久化哈希。"""

        ...

    async def verify_or_dummy(self, password: str, password_hash: PasswordHash | None) -> bool:
        """验证已有哈希；哈希不存在时执行等成本占位校验并返回假。"""

        ...

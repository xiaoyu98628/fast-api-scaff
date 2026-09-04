from pwdlib import PasswordHash as PwdlibPasswordHash

from app.contexts.user.domain.values import Password, PasswordHash


class PwdlibPasswordHasher:
    """使用 pwdlib 推荐算法生成密码哈希。"""

    def __init__(self) -> None:
        self._hasher = PwdlibPasswordHash.recommended()

    def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(self._hasher.hash(password.value))

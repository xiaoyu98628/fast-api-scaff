"""定义会话凭据值对象及令牌编解码协议。"""

import re
from dataclasses import dataclass, field
from typing import Protocol

from app.contexts.user.application.auth_errors import AuthenticationRequiredError


@dataclass(frozen=True, slots=True)
class SessionCredential:
    """保存只在应用边界流转的原始会话 Token。"""

    token: str = field(repr=False)

    def __post_init__(self) -> None:
        """限制令牌为 43 位 URL-safe 文本。"""

        if not isinstance(self.token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", self.token) is None:
            raise AuthenticationRequiredError()


class SessionTokenCodec(Protocol):
    """隔离安全随机令牌生成及摘要算法的具体实现。"""

    def issue(self) -> SessionCredential:
        """签发新的原始会话凭据。"""

        ...

    def digest(self, credential: SessionCredential) -> str:
        """生成用于查找和持久化会话的稳定摘要。"""

        ...

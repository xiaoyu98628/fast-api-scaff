"""定义认证用例的输入命令和输出 DTO。"""

from dataclasses import dataclass, field
from uuid import UUID

from app.contexts.user.application.auth_errors import InvalidCredentialsError


@dataclass(frozen=True, slots=True)
class LoginCommand:
    """保存一次登录尝试的原始用户名和密码。"""

    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        """在进入用例前限制凭据类型和输入规模。"""

        if not isinstance(self.username, str) or not 1 <= len(self.username) <= 128:
            raise InvalidCredentialsError()
        if not isinstance(self.password, str) or not 1 <= len(self.password) <= 1024:
            raise InvalidCredentialsError()


@dataclass(frozen=True, slots=True)
class TokenDTO:
    """返回新签发的访问令牌、有效期和关联用户。"""

    access_token: str = field(repr=False)
    expires_in: int
    user_id: UUID
    token_type: str = "bearer"

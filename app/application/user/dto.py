"""用户用例层数据结构（与 HTTP/Pydantic 解耦）。"""

from dataclasses import dataclass

from app.application.enums.user_status import UserStatus


@dataclass(frozen=True, slots=True)
class UserSnapshot:
    """登录成功后返回的脱敏用户信息（不含密码）。"""

    id: str
    username: str
    nickname: str
    status: UserStatus


@dataclass(frozen=True, slots=True)
class LoginResult:
    """登录用例返回：用户信息 + 访问令牌。"""

    user: UserSnapshot
    access_token: str
    token_type: str
    expires_in: int

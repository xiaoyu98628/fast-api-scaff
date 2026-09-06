import re
from dataclasses import dataclass, field
from datetime import datetime

from app.contexts.user.domain.values import UserId


@dataclass(frozen=True, slots=True)
class UserSession:
    """服务器会话，时间遵循项目本地无时区 datetime 约定。"""

    token_digest: str = field(repr=False)
    user_id: UserId
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.token_digest, str) or re.fullmatch(r"[0-9a-f]{64}", self.token_digest) is None:
            raise ValueError("会话摘要必须是 64 位小写十六进制字符串")
        if not isinstance(self.user_id, UserId):
            raise ValueError("会话用户 ID 类型不正确")
        _validate_local_datetime(self.issued_at)
        _validate_local_datetime(self.expires_at)
        if self.expires_at <= self.issued_at:
            raise ValueError("会话时间范围不合法")

    def is_valid(self, *, now: datetime) -> bool:
        _validate_local_datetime(now)
        return self.issued_at <= now < self.expires_at


def _validate_local_datetime(value: datetime) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is not None:
        raise ValueError("会话时间必须使用本地无时区 datetime")

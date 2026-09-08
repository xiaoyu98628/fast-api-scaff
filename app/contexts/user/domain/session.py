"""定义服务器端用户会话实体及其时间不变量。"""

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
        """校验令牌摘要、用户 ID 和有效时间范围。"""

        # 领域只接受固定长度的摘要形态，不直接持有会话原始 Token。
        if not isinstance(self.token_digest, str) or re.fullmatch(r"[0-9a-f]{64}", self.token_digest) is None:
            raise ValueError("会话摘要必须是 64 位小写十六进制字符串")
        if not isinstance(self.user_id, UserId):
            raise ValueError("会话用户 ID 类型不正确")
        _validate_local_datetime(self.issued_at)
        _validate_local_datetime(self.expires_at)
        if self.expires_at <= self.issued_at:
            raise ValueError("会话时间范围不合法")

    def is_valid(self, *, now: datetime) -> bool:
        """按签发时间闭区间、过期时间开区间判断会话有效性。"""

        _validate_local_datetime(now)
        return self.issued_at <= now < self.expires_at


def _validate_local_datetime(value: datetime) -> None:
    """保证会话时间遵循项目统一的本地无时区约定。"""

    if not isinstance(value, datetime) or value.utcoffset() is not None:
        raise ValueError("会话时间必须使用本地无时区 datetime")

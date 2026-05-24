from dataclasses import dataclass
from datetime import datetime

from app.domain.user.enums import UserStatus


@dataclass(frozen=True, slots=True)
class User:
    """用户领域实体。"""

    id: str
    username: str
    nickname: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime

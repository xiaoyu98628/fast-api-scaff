"""用户领域实体：封装用户核心业务规则。"""

from dataclasses import dataclass

from app.application.enums.user_status import UserStatus


@dataclass(frozen=True, slots=True)
class UserEntity:
    """用户领域实体（最小版）：仅承载登录可用性规则。"""

    id: str
    username: str
    status: UserStatus

    def can_login(self) -> bool:
        """仅激活状态允许登录。"""
        return self.status == UserStatus.ACTIVATION

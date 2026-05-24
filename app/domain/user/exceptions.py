class DomainError(Exception):
    """领域异常基类。"""


class UserNotFoundError(DomainError):
    """用户不存在。"""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user not found: {user_id}")


class UsernameAlreadyExistsError(DomainError):
    """用户名已存在。"""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"username already exists: {username}")


class InvalidUserUpdateError(DomainError):
    """用户更新参数无效。"""

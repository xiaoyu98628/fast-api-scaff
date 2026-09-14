"""定义认证用例可由入站适配器映射的边界异常。"""


class AuthApplicationError(Exception):
    """认证用例的边界错误。"""


class InvalidCredentialsError(AuthApplicationError):
    """用户名、密码或账户状态不允许登录。"""

    def __init__(self, remaining_attempts: int | None = None) -> None:
        """保存启用登录限制时可公开的剩余尝试次数。"""

        if remaining_attempts is not None and (
            not isinstance(remaining_attempts, int) or isinstance(remaining_attempts, bool) or remaining_attempts <= 0
        ):
            raise ValueError("剩余登录尝试次数必须为正整数")

        self.remaining_attempts = remaining_attempts
        super().__init__("用户名或密码错误")


class LoginTemporarilyLockedError(AuthApplicationError):
    """同一登录标识的连续失败已经触发临时锁定。"""

    def __init__(self, retry_after_seconds: int) -> None:
        """保存调用方重新尝试前需要等待的正整数秒数。"""

        if not isinstance(retry_after_seconds, int) or isinstance(retry_after_seconds, bool) or retry_after_seconds <= 0:
            raise ValueError("登录锁定等待时间必须为正整数秒")

        self.retry_after_seconds = retry_after_seconds
        super().__init__("登录尝试已被临时锁定")


class AuthenticationRequiredError(AuthApplicationError):
    """凭据缺失或会话当前不可用。"""

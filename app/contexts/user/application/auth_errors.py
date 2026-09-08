"""定义认证用例可由入站适配器映射的边界异常。"""


class AuthApplicationError(Exception):
    """认证用例的边界错误。"""


class InvalidCredentialsError(AuthApplicationError):
    """用户名、密码或账户状态不允许登录。"""


class LoginUserNotFoundError(AuthApplicationError):
    """登录时找不到对应用户。"""


class AuthenticationRequiredError(AuthApplicationError):
    """凭据缺失或会话当前不可用。"""

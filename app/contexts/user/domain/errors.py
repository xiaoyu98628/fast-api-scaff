class UserDomainError(ValueError):
    """用户领域规则被违反。"""


class InvalidUserDataError(UserDomainError):
    """用户资料不满足领域约束。"""

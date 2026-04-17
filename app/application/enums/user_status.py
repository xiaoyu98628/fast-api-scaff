"""用户状态业务枚举。"""

from enum import Enum


class UserStatus(str, Enum):
    """用户状态：激活/锁定。"""

    ACTIVATION = "activation"
    LOCKING = "locking"

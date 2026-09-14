"""定义认证用例所需的登录失败状态和限制协议。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LoginFailureStatus:
    """描述记录失败后剩余尝试次数及可选锁定时间。"""

    remaining_attempts: int
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        """确保未锁定与已锁定状态不会相互矛盾。"""

        if not isinstance(self.remaining_attempts, int) or isinstance(self.remaining_attempts, bool) or self.remaining_attempts < 0:
            raise ValueError("剩余登录尝试次数必须是非负整数")
        if self.retry_after_seconds is None:
            if self.remaining_attempts == 0:
                raise ValueError("没有剩余尝试次数时必须提供锁定时间")
            return
        if not isinstance(self.retry_after_seconds, int) or isinstance(self.retry_after_seconds, bool) or self.retry_after_seconds <= 0:
            raise ValueError("登录锁定等待时间必须为正整数秒")
        if self.remaining_attempts != 0:
            raise ValueError("登录锁定后剩余尝试次数必须为 0")


class LoginAttemptLimiter(Protocol):
    """按规范化登录标识记录失败并报告临时锁定状态。"""

    async def retry_after(self, identity: str) -> int | None:
        """返回剩余锁定秒数；当前未锁定时返回 None。"""

        ...

    async def record_failure(self, identity: str) -> LoginFailureStatus:
        """记录一次凭据失败，并返回剩余次数和可选锁定时间。"""

        ...

    async def clear(self, identity: str) -> None:
        """清除未达到阈值的历史失败记录。"""

        ...

"""定义认证用例所需的登录失败限制协议。"""

from typing import Protocol


class LoginAttemptLimiter(Protocol):
    """按规范化登录标识记录失败并报告临时锁定状态。"""

    async def retry_after(self, identity: str) -> int | None:
        """返回剩余锁定秒数；当前未锁定时返回 None。"""

        ...

    async def record_failure(self, identity: str) -> int | None:
        """记录一次凭据失败，并在触发锁定时返回等待秒数。"""

        ...

    async def clear(self, identity: str) -> None:
        """清除未达到阈值的历史失败记录。"""

        ...

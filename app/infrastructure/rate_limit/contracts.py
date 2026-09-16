"""声明限流判定契约及依赖不可用异常。"""

from dataclasses import dataclass
from typing import Protocol


class RateLimitUnavailableError(Exception):
    """表示限流存储不可用或返回了无效状态。"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """保存准入结果；拒绝时提供正整数重试等待秒数。"""

    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    """提供共享配额的原子准入判断。"""

    async def acquire(self, identity: str) -> RateLimitDecision:
        """尝试消耗一次配额；依赖故障时抛出不可用异常。"""

        ...

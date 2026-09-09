"""定义单次消息投递内的任务执行策略。"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobPolicy:
    """限制尝试次数、退避间隔和每次 handler 执行时间。"""

    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 5.0)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        """校验尝试次数、超时和退避间隔均可安全执行。"""

        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts 必须为正整数")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须为有限正数")
        if any(not math.isfinite(delay) or delay < 0 for delay in self.backoff_seconds):
            raise ValueError("退避必须为有限非负数")

    def retry_delay(self, failed_attempt: int) -> float:
        """返回本次失败后的延迟，超过配置长度时复用最后一项。"""

        if not self.backoff_seconds:
            return 0.0
        return self.backoff_seconds[min(failed_attempt - 1, len(self.backoff_seconds) - 1)]

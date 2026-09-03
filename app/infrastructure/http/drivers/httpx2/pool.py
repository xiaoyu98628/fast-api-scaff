from dataclasses import dataclass
from math import ceil


@dataclass(slots=True)
class HttpPoolRuntime:
    """单个连接池的进程内诊断计数。"""

    name: str
    limit: int
    warning_ratio: float
    active: int = 0
    peak_active: int = 0
    cancelled: int = 0
    pool_timeout: int = 0

    def acquire(self) -> bool:
        pressure_before = self.under_pressure
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        return not pressure_before and self.under_pressure

    def release(self) -> None:
        self.active = max(0, self.active - 1)

    @property
    def warning_at(self) -> int:
        return max(1, ceil(self.limit * self.warning_ratio))

    @property
    def under_pressure(self) -> bool:
        return self.active >= self.warning_at

    def log_details(self) -> dict[str, object]:
        return {
            "pool": self.name,
            "active": self.active,
            "peak_active": self.peak_active,
            "limit": self.limit,
            "usage": round(self.active / self.limit, 4),
            "cancelled": self.cancelled,
            "pool_timeout": self.pool_timeout,
        }

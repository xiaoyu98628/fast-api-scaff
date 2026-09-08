"""维护不依赖 HTTPX2 私有连接池状态的应用侧诊断计数。"""

from dataclasses import dataclass
from math import ceil


@dataclass(slots=True)
class HttpPoolRuntime:
    """统计活跃请求上下文；active 不代表底层物理连接数量。"""

    name: str
    limit: int
    warning_ratio: float
    active: int = 0
    peak_active: int = 0
    cancelled: int = 0
    pool_timeout: int = 0

    def acquire(self) -> bool:
        """登记请求，并仅在本轮首次跨过压力阈值时返回 True。"""

        pressure_before = self.under_pressure
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        return not pressure_before and self.under_pressure

    def release(self) -> None:
        """释放一个请求计数，并防止异常路径产生负值。"""

        self.active = max(0, self.active - 1)

    @property
    def warning_at(self) -> int:
        """把比例阈值向上取整为至少一个活跃请求。"""

        return max(1, ceil(self.limit * self.warning_ratio))

    @property
    def under_pressure(self) -> bool:
        """判断当前应用侧活跃数是否达到告警阈值。"""

        return self.active >= self.warning_at

    def log_details(self) -> dict[str, object]:
        """生成不读取 HTTPX2 私有状态的低基数诊断字段。"""

        return {
            "pool": self.name,
            "active": self.active,
            "peak_active": self.peak_active,
            "limit": self.limit,
            "usage": round(self.active / self.limit, 4),
            "cancelled": self.cancelled,
            "pool_timeout": self.pool_timeout,
        }

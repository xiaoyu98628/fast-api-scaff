"""健康检查相关业务码低位（BB×100+CC）；支持 message 与 HTTP 状态码。"""

from enum import IntEnum

class HealthErrorCode(IntEnum):
    """健康检查模块业务码低位（BB×100+CC）。"""

    DB_PROBE_FAILED = 9001
    REDIS_PROBE_FAILED = 9002

    def message(self) -> str:
        return {
            HealthErrorCode.DB_PROBE_FAILED: "数据库探活失败",
            HealthErrorCode.REDIS_PROBE_FAILED: "Redis 探活失败",
        }[self]

    def status_code(self) -> int:
        return 500

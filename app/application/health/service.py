"""系统级健康检查用例：编排 DB / Redis 基础设施，供接口层调用。"""

from sqlalchemy import text

from app.application.health.errors import HealthErrorCode
from app.common.errors.system_exception import SystemException
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.redis.client import ping_redis


class SystemHealthService:
    """系统连通性等用例（应用层编排基础设施，不在此处理 HTTP）。"""

    async def db_select_one(self) -> int:
        """执行 ``SELECT 1``，用于探活；返回标量结果。"""
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                result = await session.execute(text("SELECT 1 AS ok"))
                row = result.mappings().one()
                return int(row["ok"])
        except Exception as e:
            raise SystemException(HealthErrorCode.DB_PROBE_FAILED) from e

    async def redis_ping(self) -> bool:
        """委托基础设施层对 Redis 执行 PING。"""
        try:
            return await ping_redis()
        except Exception as e:
            raise SystemException(HealthErrorCode.REDIS_PROBE_FAILED) from e

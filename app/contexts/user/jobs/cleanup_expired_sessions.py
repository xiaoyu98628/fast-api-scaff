"""提供清理过期用户会话的异步任务。"""

import logging
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError, DisconnectionError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.infrastructure.logging.record import log_extra
from app.infrastructure.queue.errors import RetryableJobError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CleanupExpiredSessionsJob(QueueJob[JobExecutionContext]):
    """通过用户认证应用服务清理过期会话。"""

    async def handle(self, context: JobExecutionContext) -> None:
        """执行清理，并把明确的暂时性数据库故障转换为可重试错误。"""

        try:
            removed_count = await context.container.users.auth.cleanup_expired_sessions()
        except (DisconnectionError, SQLAlchemyTimeoutError) as error:
            raise RetryableJobError("清理过期用户会话时数据库暂时不可用") from error
        except DBAPIError as error:
            if not error.connection_invalidated:
                raise
            raise RetryableJobError("清理过期用户会话时数据库连接已失效") from error

        _logger.info(
            "过期用户会话清理完成。",
            extra=log_extra(
                "user.sessions.expired_removed",
                removed_count=removed_count,
            ),
        )

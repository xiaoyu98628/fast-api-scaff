"""提供登录成功后通过应用服务读取用户数据的异步任务示例。"""

import logging
from dataclasses import dataclass
from uuid import UUID

from app.contexts.user.application.errors import UserNotFoundError
from app.infrastructure.logging.record import log_extra
from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext

LOGIN_SUCCEEDED_MESSAGE = "用户登录成功，队列任务已执行。"
_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginSucceededJob(QueueJob[JobExecutionContext]):
    """携带用户 ID，并在 Worker 执行时读取当前用户快照。"""

    # 可空用于兼容增加 user_id 字段前已经进入队列的消息。
    user_id: UUID | None = None
    message: str = LOGIN_SUCCEEDED_MESSAGE

    def __post_init__(self) -> None:
        """校验反序列化后的兼容字段和固定消息。"""

        if self.user_id is not None and not isinstance(self.user_id, UUID):
            raise ValueError("登录成功任务用户 ID 不合法")
        if self.message != LOGIN_SUCCEEDED_MESSAGE:
            raise ValueError("登录成功任务消息不合法")

    async def handle(self, context: JobExecutionContext) -> None:
        """通过用户应用服务查询数据库，并记录不含认证秘密的用户快照。"""

        if self.user_id is None:
            # 旧消息没有用户 ID，无法查询数据库；保留原有可消费行为。
            _logger.info(
                self.message,
                extra=log_extra("user.login_succeeded", user_id=None, user_status=None),
            )
            return

        try:
            user = await context.container.users.service.get(self.user_id)
        except UserNotFoundError:
            # 登录和异步消费之间允许用户被删除；重试不会改变这一永久状态。
            _logger.warning(
                "登录成功任务执行时用户已不存在。",
                extra=log_extra("user.login_succeeded.user_missing", user_id=str(self.user_id)),
            )
            return

        _logger.info(
            self.message,
            extra=log_extra(
                "user.login_succeeded",
                user_id=str(self.user_id),
                user_status=user.status.value,
            ),
        )

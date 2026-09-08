import logging
from dataclasses import dataclass

from app.infrastructure.logging.record import log_extra
from app.infrastructure.queue.job import QueueJob

LOGIN_SUCCEEDED_MESSAGE = "用户登录成功，队列任务已执行。"
_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginSucceededJob(QueueJob):
    message: str = LOGIN_SUCCEEDED_MESSAGE

    def __post_init__(self) -> None:
        if self.message != LOGIN_SUCCEEDED_MESSAGE:
            raise ValueError("登录成功任务消息不合法")

    async def handle(self) -> None:
        _logger.info(self.message, extra=log_extra("user.login_succeeded"))

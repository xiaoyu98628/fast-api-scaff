"""声明用户会话相关的定时计划。"""

from app.contexts.user.jobs.cleanup_expired_sessions import CleanupExpiredSessionsJob
from app.interfaces.scheduler.contracts import CronSchedule, QueueJobSchedule
from app.interfaces.scheduler.registry import ScheduleRegistry


def register_schedules(registry: ScheduleRegistry) -> None:
    """注册用户会话定时计划。"""

    registry.add(
        QueueJobSchedule(
            id="users.sessions.cleanup_expired",
            trigger=CronSchedule(hour=0, minute=0),
            job=CleanupExpiredSessionsJob(),
        )
    )

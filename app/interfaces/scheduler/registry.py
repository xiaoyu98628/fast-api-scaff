"""保存并校验当前部署声明的定时计划。"""

from app.interfaces.scheduler.contracts import QueueJobSchedule


class ScheduleRegistry:
    """维护使用稳定 ID 索引的不可重复计划集合。"""

    def __init__(self) -> None:
        """创建空的计划注册表。"""

        self._definitions: dict[str, QueueJobSchedule] = {}

    def add(self, definition: QueueJobSchedule) -> None:
        """增加一个计划，并拒绝重复计划 ID。"""

        if not isinstance(definition, QueueJobSchedule):
            raise TypeError("只能注册 QueueJobSchedule")
        if definition.id in self._definitions:
            raise ValueError(f"定时计划 ID {definition.id!r} 重复")
        self._definitions[definition.id] = definition

    @property
    def definitions(self) -> tuple[QueueJobSchedule, ...]:
        """按计划 ID 稳定返回不可变计划快照。"""

        return tuple(self._definitions[key] for key in sorted(self._definitions))

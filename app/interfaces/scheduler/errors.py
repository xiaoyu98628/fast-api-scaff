"""定义 Scheduler 宿主对外暴露的稳定错误。"""


class SchedulerError(RuntimeError):
    """表示调度引擎配置或运行失败。"""


class SchedulerConfigurationError(SchedulerError):
    """表示代码计划发现、声明或 Trigger 配置无效。"""

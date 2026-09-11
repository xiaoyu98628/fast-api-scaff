"""定义队列任务可访问的 Worker 宿主上下文。"""

from dataclasses import dataclass

from app.config.settings import Settings
from app.runtime.container import ApplicationContainer


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """保存队列任务执行期间可使用的配置和应用容器。"""

    settings: Settings
    container: ApplicationContainer

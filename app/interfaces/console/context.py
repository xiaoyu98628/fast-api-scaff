from dataclasses import dataclass

from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings


@dataclass(frozen=True, slots=True)
class ConsoleContext:
    """保存一次 Console 命令可使用的应用上下文。"""

    settings: Settings
    container: ApplicationContainer

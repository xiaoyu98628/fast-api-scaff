from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    """解析后的单个日志通道。"""

    name: str
    logger: str
    path: Path
    level: str
    driver: str
    also: tuple[str, ...] = ()
    console: bool = False

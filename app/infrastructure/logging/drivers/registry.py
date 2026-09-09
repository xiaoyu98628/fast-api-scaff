"""维护日志 driver 名称到 Handler Builder 的显式映射。"""

from collections.abc import Iterable

from app.infrastructure.logging.contracts.driver import (
    LoggingDriverBuilder,
    LoggingDriverRegistration,
)
from app.infrastructure.logging.drivers.stream import build_stream_handler
from app.infrastructure.logging.errors import LoggingConfigurationError


class LoggingDriverRegistry:
    """显式注册并按名称查找日志 Driver Builder。"""

    def __init__(self, registrations: Iterable[LoggingDriverRegistration]) -> None:
        """注册 Builder，并拒绝空名称、重复名称和不可调用对象。"""

        self._registered = tuple(registrations)
        self._drivers: dict[str, LoggingDriverBuilder] = {}

        # 构建时拒绝空名称和重复注册，避免扩展顺序造成静默覆盖。
        for name, builder in self._registered:
            if not name.strip():
                raise LoggingConfigurationError("日志驱动名称不能为空")
            if name in self._drivers:
                raise LoggingConfigurationError(f"日志驱动 {name!r} 重复注册")
            if not callable(builder):
                raise LoggingConfigurationError(f"日志驱动 {name!r} Builder 不可调用")
            self._drivers[name] = builder

    @property
    def drivers(self) -> tuple[str, ...]:
        """按注册顺序返回全部 driver 名称。"""

        return tuple(self._drivers)

    def get(self, name: str) -> LoggingDriverBuilder | None:
        """按名称返回 Builder；未注册时返回 None。"""

        return self._drivers.get(name)

    def extended(self, *registrations: LoggingDriverRegistration) -> LoggingDriverRegistry:
        """返回包含额外驱动的新注册表，不修改当前实例。"""

        return LoggingDriverRegistry((*self._registered, *registrations))

    def replaced(self, name: str, builder: LoggingDriverBuilder) -> LoggingDriverRegistry:
        """显式替换已有 Builder，并返回独立的新注册表。"""

        if name not in self._drivers:
            raise LoggingConfigurationError(f"日志驱动 {name!r} 未注册，不能替换")

        return LoggingDriverRegistry(
            (registered_name, builder if registered_name == name else registered_builder) for registered_name, registered_builder in self._registered
        )


DEFAULT_LOGGING_DRIVERS = LoggingDriverRegistry((("stream", build_stream_handler),))

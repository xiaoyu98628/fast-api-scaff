"""声明日志驱动注册和构建过程使用的公共类型。"""

from collections.abc import Callable

type LoggingHandlerConfig = dict[str, object]
type LoggingDriverBuilder = Callable[[dict[str, object]], LoggingHandlerConfig]
type LoggingDriverRegistration = tuple[str, LoggingDriverBuilder]

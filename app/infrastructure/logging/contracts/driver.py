from collections.abc import Callable

type LoggingHandlerConfig = dict[str, object]
type LoggingDriverBuilder = Callable[[dict[str, object]], LoggingHandlerConfig]

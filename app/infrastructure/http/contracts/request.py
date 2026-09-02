from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class HttpUnset:
    """表示调用方没有提供可选请求值。"""

    __slots__ = ()


HTTP_UNSET = HttpUnset()


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpRequest:
    """驱动无关的单次 HTTP 请求。"""

    method: str
    url: str
    operation: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, object] = field(default_factory=dict)
    content: bytes | str | None = None
    json: object = HTTP_UNSET
    timeout: float | None = None

    def __post_init__(self) -> None:
        method = self.method.strip().upper()

        try:
            parsed_url = urlsplit(self.url)
            port = parsed_url.port
        except ValueError as error:
            raise ValueError("HTTP url 必须包含有效的主机名和端口") from error

        if not method:
            raise ValueError("HTTP method 不能为空")
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("HTTP url 必须是包含主机名的 http/https 绝对地址")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("HTTP url 端口必须在 1 到 65535 之间")
        if self.content is not None and self.json is not HTTP_UNSET:
            raise ValueError("content 和 json 不能同时提供")
        if self.operation is not None and not self.operation.strip():
            raise ValueError("HTTP operation 有值时不能为空")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("HTTP timeout 必须大于 0")

        object.__setattr__(self, "method", method)

class HttpError(RuntimeError):
    """HTTP 出站基础能力异常基类。"""


class HttpConfigurationError(HttpError):
    """HTTP 出站配置不合法。"""


class HttpTransportError(HttpError):
    """HTTP 请求因网络或传输协议失败。"""


class HttpTimeoutError(HttpTransportError):
    """HTTP 请求阶段超时。"""


class HttpPoolTimeoutError(HttpTimeoutError):
    """HTTP 请求等待连接池容量超时。"""


class HttpResponseTooLargeError(HttpError):
    """普通 HTTP 响应超过允许的缓冲大小。"""

    def __init__(self, max_response_bytes: int) -> None:
        self.max_response_bytes = max_response_bytes
        super().__init__(f"HTTP 响应体超过 {max_response_bytes} 字节限制")

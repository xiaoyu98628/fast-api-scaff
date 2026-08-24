from collections.abc import Mapping

from app.interfaces.http.shared.response.codes.contract import CodeContract


class HttpError(Exception):
    """由 HTTP 接口层抛出的、携带明确响应码的异常。"""

    __slots__ = ("code", "data", "headers", "message")

    code: CodeContract
    message: str
    data: object | None
    headers: dict[str, str] | None

    def __init__(
        self,
        code: CodeContract,
        *,
        message: str | None = None,
        data: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if code.status_code < 400:
            raise ValueError("HTTP 异常必须使用 4xx 或 5xx 响应码")

        resolved_message = message if message is not None else code.message

        self.code = code
        self.message = resolved_message
        self.data = data
        self.headers = dict(headers) if headers is not None else None

        super().__init__(resolved_message)

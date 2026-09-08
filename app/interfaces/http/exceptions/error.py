"""定义携带统一响应码和可选响应数据的 HTTP 边界异常。"""

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
        """校验错误状态码并保存渲染响应所需的信息。"""

        if code.status_code < 400:
            raise ValueError("HTTP 异常必须使用 4xx 或 5xx 响应码")

        resolved_message = message if message is not None else code.message

        self.code = code
        self.message = resolved_message
        self.data = data
        # 复制调用方映射，避免异常创建后响应头被外部修改。
        self.headers = dict(headers) if headers is not None else None

        super().__init__(resolved_message)

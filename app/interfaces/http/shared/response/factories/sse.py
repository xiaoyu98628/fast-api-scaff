"""构造统一 SSE 成功、业务错误和完成事件。"""

from dataclasses import dataclass

from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.contract import CodeContract
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.sse import SseResponse

_RESERVED_EVENTS = frozenset({"business_error", "done"})


@dataclass(frozen=True, slots=True)
class SseResponseFactory:
    """构造 SSE 事件，不负责发送事件、捕获异常或终止数据流。"""

    code_builder: ResponseCodeBuilder

    def success(
        self,
        data: object,
        *,
        event: str = "message",
        id: str | None = None,
        retry: int | None = None,
    ) -> SseResponse:
        """构造成功事件；数据须可序列化为 JSON，非法事件字段会抛出 ValueError。"""

        # 保留控制事件名，避免普通数据被客户端误判为失败或结束。
        if not event or event in _RESERVED_EVENTS:
            raise ValueError("成功事件名称不能为空或使用保留名称")

        # FastAPI 对 data=None 省略 data 行；显式 null 确保该事件仍能被客户端接收。
        if data is None:
            return SseResponse(event=event, raw_data="null", id=id, retry=retry)

        return SseResponse(event=event, data=data, id=id, retry=retry)

    def error(
        self,
        code: CodeContract = ErrorCode.INTERNAL_ERROR,
        *,
        message: str | None = None,
        data: object | None = None,
    ) -> SseResponse:
        """构造业务错误事件；5xx 统一隐藏调用方提供的文案和数据。"""

        if not 400 <= code.status_code < 600:
            raise ValueError("错误事件必须使用 4xx 或 5xx 响应码")

        # 与普通 JSON 异常边界保持一致，防止内部异常、SQL 或上游详情进入响应。
        if code.status_code >= 500:
            code = ErrorCode.INTERNAL_ERROR
            message = None
            data = None

        payload: dict[str, object] = {
            "code": self.code_builder.build(code),
            "message": message if message is not None else code.message,
        }
        if data is not None:
            payload["data"] = data

        return SseResponse(event="business_error", data=payload)

    def done(self) -> SseResponse:
        """构造完成事件；调用方仍需结束生成器，客户端应关闭连接。"""

        return SseResponse(event="done", data={})

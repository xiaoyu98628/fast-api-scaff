"""构造统一 SSE 成功、业务错误和完成事件。"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from fastapi.encoders import jsonable_encoder

from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.contract import CodeContract
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.sse import SseResponse

_STREAM_ERROR_EVENT = "stream_error"
_DONE_EVENT = "done"
_RESERVED_EVENTS = frozenset({_STREAM_ERROR_EVENT, _DONE_EVENT})


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

        return SseResponse(
            event=event,
            raw_data=_serialize_json_data(data),
            id=id,
            retry=retry,
        )

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

        return SseResponse(
            event=_STREAM_ERROR_EVENT,
            raw_data=_serialize_json_data(payload),
        )

    def done(self) -> SseResponse:
        """构造完成事件；调用方仍需结束生成器，客户端应关闭连接。"""

        return SseResponse(event=_DONE_EVENT, data={})


def _serialize_json_data(data: object) -> str:
    """按 FastAPI SSE 规则把事件数据一次性序列化为 JSON 字符串。"""

    missing = object()
    try:
        model_dump_json = getattr(data, "model_dump_json", missing)
        if model_dump_json is missing:
            return json.dumps(jsonable_encoder(data))

        if not callable(model_dump_json):
            raise TypeError("model_dump_json 必须可调用")

        serialized = cast(Callable[[], object], model_dump_json)()
        if not isinstance(serialized, str):
            raise TypeError("model_dump_json 必须返回字符串")

        return serialized
    except Exception as error:
        raise ValueError("SSE 事件数据必须可以序列化为 JSON") from error

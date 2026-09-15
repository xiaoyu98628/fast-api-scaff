"""提供有限事件流及可控处理失败的 SSE HTTP 接口。"""

from asyncio import sleep
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.sse import EventSourceResponse

from app.interfaces.http.controllers.v1.streams.openapi import STREAM_VALIDATION_ERROR_RESPONSE
from app.interfaces.http.controllers.v1.streams.schemas import EventStreamParams
from app.interfaces.http.dependencies.response import SseResponseFactoryDependency
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.exceptions.sse import handle_sse_exceptions
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.factories.sse import SseResponseFactory
from app.interfaces.http.shared.response.sse import SseResponse

router = APIRouter(prefix="/streams", tags=["streams"])


@router.get(
    "/events",
    response_class=EventSourceResponse,
    summary="获取有限 SSE 事件流",
    description="首条立即发送，后续每秒一条。fail_at 用于模拟处理失败；不支持断点续传。",
    responses={422: STREAM_VALIDATION_ERROR_RESPONSE},
)
async def stream_events(
    responses: SseResponseFactoryDependency,
    params: Annotated[EventStreamParams, Query()],
) -> AsyncIterator[SseResponse]:
    """发送经过统一流内异常边界处理的 SSE 事件。"""

    events = _generate_events(params, responses)
    async for event in handle_sse_exceptions(events, responses):
        yield event


async def _generate_events(
    params: EventStreamParams,
    responses: SseResponseFactory,
) -> AsyncGenerator[SseResponse]:
    """按序生成消息；正常完成发送 done，模拟失败交给异常边界。"""

    for sequence in range(1, params.count + 1):
        if sequence > 1:
            # 允许客户端断开时的取消继续传播，避免继续生成无接收方的数据。
            await sleep(1)

        if sequence == params.fail_at:
            raise HttpError(
                ErrorCode.INTERNAL_ERROR,
                message="SSE 事件流：模拟处理失败",
                data={"sequence": sequence},
            )

        yield responses.success(
            {"sequence": sequence, "content": f"第 {sequence} 条消息"},
            id=str(sequence),
        )

    yield responses.done()

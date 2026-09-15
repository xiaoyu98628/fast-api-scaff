"""把 SSE 业务生成器中的异常转换为安全的终止事件。"""

import logging
from asyncio import CancelledError
from collections.abc import AsyncGenerator, AsyncIterator

from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.middleware.logging import HttpLogEvent
from app.interfaces.http.shared.response.factories.sse import SseResponseFactory
from app.interfaces.http.shared.response.sse import SseResponse

_LOGGER = logging.getLogger("app.interfaces.http.sse")


async def handle_sse_exceptions(
    events: AsyncGenerator[SseResponse],
    responses: SseResponseFactory,
) -> AsyncIterator[SseResponse]:
    """转换业务生成器异常，并确保上游异步生成器被关闭。

    HTTP 响应开始后无法再修改状态码或响应头，因此忽略 HttpError
    携带的 headers；客户端断开产生的取消必须继续传播。
    """

    try:
        async for event in events:
            yield event
    except CancelledError:
        raise
    except HttpError as error:
        if error.code.status_code >= 500:
            _log_stream_failure(error)

        yield responses.error(
            error.code,
            message=error.message,
            data=error.data,
        )
    except Exception as error:
        _log_stream_failure(error)
        yield responses.error()
    finally:
        await events.aclose()


def _log_stream_failure(error: BaseException) -> None:
    """记录异常类型和调用位置，不记录异常消息或业务数据。"""

    error_type, stacktrace = safe_exception_details(error)
    _LOGGER.error(
        "SSE stream failed",
        extra=log_extra(
            HttpLogEvent.SSE_STREAM_FAILED,
            error_type=error_type,
            stacktrace=stacktrace,
        ),
    )

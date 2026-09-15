"""验证 SSE 工厂协议、HTTP 装配、错误边界与断开清理。"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator

import pytest
from fastapi import Depends, HTTPException
from fastapi.sse import EventSourceResponse
from httpx2 import ASGITransport, AsyncClient
from starlette.types import Message

from app.bootstrap.http.application import create_app
from app.interfaces.http.dependencies.response import SseResponseFactoryDependency
from app.interfaces.http.exceptions.error import HttpError
from app.interfaces.http.exceptions.sse import handle_sse_exceptions
from app.interfaces.http.middleware.logging import HttpLogEvent
from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.contract import CodeDefinition
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.factories.sse import SseResponseFactory
from app.interfaces.http.shared.response.sse import SseResponse
from tests.http.test_response import build_settings


def test_error_payload_reuses_codes_and_omits_optional_data() -> None:
    factory = SseResponseFactory(ResponseCodeBuilder("321"))
    assert _event_json(factory.error()) == {
        "code": "5003210101",
        "message": ErrorCode.INTERNAL_ERROR.message,
    }
    assert _event_json(factory.error(ErrorCode.INTERNAL_ERROR, message="sensitive", data={"sql": "secret"})) == {
        "code": "5003210101",
        "message": ErrorCode.INTERNAL_ERROR.message,
    }
    error = factory.error(ErrorCode.RESOURCE_NOT_FOUND, message="", data={"task": 1})
    assert error.event == "stream_error"
    assert _event_json(error) == {"code": "4043210102", "message": "", "data": {"task": 1}}
    custom = CodeDefinition(code="1234", message="任务失败", status_code=409)
    assert _event_json(factory.error(custom)) == {"code": "4093211234", "message": "任务失败"}
    with pytest.raises(ValueError, match="4xx 或 5xx"):
        factory.error(SuccessCode.OK)


@pytest.mark.asyncio
async def test_unknown_stream_error_becomes_sanitized_terminal_event(caplog: pytest.LogCaptureFixture) -> None:
    factory = SseResponseFactory(ResponseCodeBuilder("321"))

    async def events() -> AsyncGenerator[SseResponse]:
        yield factory.success({"sequence": 1})
        raise RuntimeError("sensitive stream detail")

    caplog.set_level(logging.ERROR, logger="app.interfaces.http.sse")
    rendered = [event async for event in handle_sse_exceptions(events(), factory)]

    assert [event.event for event in rendered] == ["message", "stream_error"]
    assert _event_json(rendered[-1]) == {
        "code": "5003210101",
        "message": ErrorCode.INTERNAL_ERROR.message,
    }
    records = [record for record in caplog.records if record.name == "app.interfaces.http.sse"]
    assert len(records) == 1
    assert getattr(records[0], "event", None) is HttpLogEvent.SSE_STREAM_FAILED
    assert getattr(records[0], "details")["error_type"] == "builtins.RuntimeError"
    assert "sensitive stream detail" not in repr(records[0].__dict__)


@pytest.mark.asyncio
async def test_non_serializable_success_becomes_stream_error(caplog: pytest.LogCaptureFixture) -> None:
    factory = SseResponseFactory(ResponseCodeBuilder("321"))

    async def events() -> AsyncGenerator[SseResponse]:
        yield factory.success({"value": 1 + 2j})

    caplog.set_level(logging.ERROR, logger="app.interfaces.http.sse")
    rendered = [event async for event in handle_sse_exceptions(events(), factory)]

    assert [event.event for event in rendered] == ["stream_error"]
    assert _event_json(rendered[0]) == {
        "code": "5003210101",
        "message": ErrorCode.INTERNAL_ERROR.message,
    }
    record = next(record for record in caplog.records if record.name == "app.interfaces.http.sse")
    assert getattr(record, "details")["error_type"] == "builtins.ValueError"


@pytest.mark.asyncio
async def test_non_serializable_http_error_data_falls_back_to_safe_stream_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = SseResponseFactory(ResponseCodeBuilder("321"))

    async def events() -> AsyncGenerator[SseResponse]:
        yield factory.success({"sequence": 1})
        raise HttpError(ErrorCode.RESOURCE_NOT_FOUND, data={"value": 1 + 2j})

    caplog.set_level(logging.ERROR, logger="app.interfaces.http.sse")
    rendered = [event async for event in handle_sse_exceptions(events(), factory)]

    assert [event.event for event in rendered] == ["message", "stream_error"]
    assert _event_json(rendered[-1]) == {
        "code": "5003210101",
        "message": ErrorCode.INTERNAL_ERROR.message,
    }
    record = next(record for record in caplog.records if record.name == "app.interfaces.http.sse")
    assert getattr(record, "details")["error_type"] == "builtins.ValueError"


@pytest.mark.parametrize("event", ["", "done", "stream_error", "delta\ninjected", "delta\rinjected"])
def test_success_rejects_invalid_event_names(event: str) -> None:
    with pytest.raises(ValueError):
        SseResponseFactory(ResponseCodeBuilder("001")).success({}, event=event)


@pytest.mark.parametrize("event_id", ["1\n2", "1\r2", "1\x002"])
def test_success_rejects_invalid_ids(event_id: str) -> None:
    with pytest.raises(ValueError):
        SseResponseFactory(ResponseCodeBuilder("001")).success({}, id=event_id)


@pytest.mark.parametrize(
    ("model_dump_json", "expected_cause"),
    [
        (None, "model_dump_json 必须可调用"),
        (1, "model_dump_json 必须可调用"),
        (staticmethod(lambda: {"value": 1}), "model_dump_json 必须返回字符串"),
    ],
)
def test_success_rejects_invalid_model_dump_json(model_dump_json: object, expected_cause: str) -> None:
    payload = type("Payload", (), {"model_dump_json": model_dump_json})()

    with pytest.raises(ValueError, match="必须可以序列化") as exc_info:
        SseResponseFactory(ResponseCodeBuilder("001")).success(payload)

    assert str(exc_info.value.__cause__) == expected_cause


@pytest.mark.asyncio
async def test_http_sse_serializes_payload_only_once() -> None:
    app = create_app(build_settings())

    class SingleUsePayload:
        calls = 0

        def model_dump_json(self) -> str:
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("payload was serialized twice")
            return '{"value": 1}'

    payload = SingleUsePayload()

    @app.get("/stream-once", response_class=EventSourceResponse)
    async def stream(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
        yield responses.success(payload)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/stream-once")

    assert response.status_code == 200
    assert json.loads(response.text.split("data: ", 1)[1]) == {"value": 1}
    assert payload.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("service_code", ["001", "321"])
async def test_http_sse_payloads_headers_and_openapi(service_code: str) -> None:
    app = create_app(build_settings(service_code))

    @app.get("/stream", response_class=EventSourceResponse)
    async def stream(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
        yield responses.success({"content": "你好\n世界"}, event="delta", id="1", retry=1000)
        yield responses.success(None)
        yield responses.done()

    @app.get("/failure", response_class=EventSourceResponse)
    async def failure(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
        yield responses.error(ErrorCode.RESOURCE_NOT_FOUND)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/stream")
        failure_response = await client.get("/failure")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"]
    assert response.headers["x-accel-buffering"] == "no"
    blocks = response.text.strip().split("\n\n")
    first = dict(line.split(": ", 1) for line in blocks[0].splitlines())
    assert first == {"event": "delta", "data": first["data"], "id": "1", "retry": "1000"}
    assert json.loads(first["data"]) == {"content": "你好\n世界"}
    assert blocks[1] == "event: message\ndata: null"
    assert blocks[2] == "event: done\ndata: {}"
    assert failure_response.status_code == 200
    error_lines = failure_response.text.strip().splitlines()
    assert error_lines[0] == "event: stream_error"
    assert json.loads(error_lines[1].removeprefix("data: ")) == {
        "code": f"404{service_code}0102",
        "message": ErrorCode.RESOURCE_NOT_FOUND.message,
    }
    content = app.openapi()["paths"]["/stream"]["get"]["responses"]["200"]["content"]
    assert "text/event-stream" in content
    assert "application/json" not in content
    assert app.state.json_response_factory.code_builder is app.state.sse_response_factory.code_builder


@pytest.mark.asyncio
async def test_dependency_failure_remains_json_before_stream() -> None:
    app = create_app(build_settings())

    async def reject() -> None:
        raise HTTPException(status_code=401, detail="需要登录")

    @app.get("/stream", response_class=EventSourceResponse, dependencies=[Depends(reject)])
    async def stream(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
        yield responses.done()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/stream")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_disconnect_finalizes_generator() -> None:
    app = create_app(build_settings())
    sent = asyncio.Event()
    closed = asyncio.Event()

    @app.get("/stream", response_class=EventSourceResponse)
    async def stream(responses: SseResponseFactoryDependency) -> AsyncIterator[SseResponse]:
        try:
            yield responses.success({"value": 1})
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def receive() -> Message:
        # 首条数据实际发出后才断开，验证正在运行的生成器能被清理。
        await sent.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            sent.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 123),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert sent.is_set()
    assert closed.is_set()


def _event_json(event: SseResponse) -> object:
    """读取工厂已经序列化并交给 FastAPI 直接发送的 JSON 数据。"""

    assert event.data is None
    assert event.raw_data is not None
    return json.loads(event.raw_data)

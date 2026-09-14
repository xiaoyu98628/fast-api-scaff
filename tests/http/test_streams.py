"""验证注册的 SSE 事件流、参数校验、模拟错误及断开取消行为。"""

import asyncio
import json

import pytest
from httpx2 import ASGITransport, AsyncClient
from starlette.types import Message

import app.interfaces.http.controllers.v1.streams.router as stream_module
from app.bootstrap.http.application import create_app
from tests.http.test_response import build_settings


@pytest.mark.asyncio
@pytest.mark.parametrize("query,count", [("", 5), ("?count=1", 1), ("?count=20", 20)])
async def test_event_stream_success(query: str, count: int, monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(stream_module, "sleep", sleep)
    app = create_app(build_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/streams/events{query}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"]
    events = [dict(line.split(": ", 1) for line in block.splitlines()) for block in response.text.strip().split("\n\n")]
    assert len(events) == count + 1
    for sequence, event in enumerate(events[:-1], 1):
        assert event["event"] == "message"
        assert event["id"] == str(sequence)
        assert json.loads(event["data"]) == {"sequence": sequence, "content": f"第 {sequence} 条消息"}
    assert events[-1] == {"event": "done", "data": "{}"}
    assert delays == [1] * (count - 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_at", [1, 3, 5])
async def test_failure_terminates_without_done(fail_at: int, monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(stream_module, "sleep", sleep)
    app = create_app(build_settings("321"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/streams/events?count=5&fail_at={fail_at}")
    assert response.status_code == 200
    events = [dict(line.split(": ", 1) for line in block.splitlines()) for block in response.text.strip().split("\n\n")]
    assert [event["event"] for event in events] == ["message"] * (fail_at - 1) + ["business_error"]
    assert [event["id"] for event in events[:-1]] == [str(i) for i in range(1, fail_at)]
    assert json.loads(events[-1]["data"]) == {
        "code": "5003210101",
        "message": "SSE 事件流：模拟处理失败",
        "data": {"sequence": fail_at},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["count=0", "count=21", "count=x", "fail_at=0", "fail_at=21", "fail_at=x", "count=2&fail_at=3", "unknown=1"])
async def test_invalid_query_returns_json_before_stream(query: str) -> None:
    app = create_app(build_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/streams/events?{query}")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "4220010101"
    assert body["data"]
    assert body["request_id"] == response.headers["x-request-id"]


def test_openapi_matches_stream_and_json_validation_contracts() -> None:
    schema = create_app(build_settings()).openapi()
    operation = schema["paths"]["/api/v1/streams/events"]["get"]
    assert operation["tags"] == ["streams"]
    parameters = {param["name"]: param["schema"] for param in operation["parameters"]}
    assert parameters["count"]["default"] == 5
    assert parameters["count"]["minimum"] == 1
    assert parameters["count"]["maximum"] == 20
    assert "fail_at" in parameters
    assert set(operation["responses"]["200"]["content"]) == {"text/event-stream"}
    validation_content = operation["responses"]["422"]["content"]
    assert set(validation_content) == {"application/json"}
    validation_schema = validation_content["application/json"]["schema"]
    assert {"code", "success", "message", "data", "request_id"} <= validation_schema["properties"].keys()
    details = next(item for item in validation_schema["properties"]["data"]["anyOf"] if item.get("type") == "array")
    assert set(details["items"]["required"]) == {"type", "location", "message"}
    assert "$ref" not in json.dumps(validation_schema)

    # 对照原生统一错误模型，避免局部内联声明在模型演进后静默过期。
    components = schema["components"]["schemas"]
    user_schema = schema["paths"]["/api/v1/users"]["get"]["responses"]["422"]["content"]["application/json"]["schema"]

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            if "$ref" in value:
                return normalize(components[value["$ref"].rsplit("/", 1)[-1]])
            return {key: normalize(item) for key, item in value.items() if key != "title"}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    assert normalize(validation_schema) == normalize(user_schema)


@pytest.mark.asyncio
async def test_disconnect_cancels_pending_stream_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    waiting = asyncio.Event()
    cancelled = asyncio.Event()
    messages: list[Message] = []

    async def sleep(delay: float) -> None:
        waiting.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(stream_module, "sleep", sleep)
    app = create_app(build_settings())

    async def receive() -> Message:
        # 等待路由进入第二条消息前的间隔，确保取消发生于活动生成器中。
        await waiting.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/streams/events",
        "raw_path": b"/api/v1/streams/events",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 123),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert cancelled.is_set()
    bodies = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    assert b"event: done" not in bodies
    assert b"id: 2" not in bodies

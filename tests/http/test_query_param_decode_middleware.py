from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, Request
from httpx2 import ASGITransport, AsyncClient
from starlette.middleware import Middleware
from starlette.types import Message, Scope

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.interfaces.http.middleware.query_param_decode import DECODED_F_STATE_KEY, QueryParamDecodeMiddleware, encode_query_param


def create_query_app() -> FastAPI:
    app = FastAPI(middleware=[Middleware(QueryParamDecodeMiddleware)])

    @app.get("/query")
    async def read_query(request: Request) -> dict[str, object]:
        return {
            "query": list(request.query_params.multi_items()),
            "decoded": getattr(request.state, DECODED_F_STATE_KEY, None),
        }

    return app


@asynccontextmanager
async def create_test_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def test_query_param_decode_middleware_is_registered() -> None:
    app = create_app(build_settings())

    assert any(middleware.cls is QueryParamDecodeMiddleware for middleware in app.user_middleware)


@pytest.mark.asyncio
async def test_request_without_encoded_param_is_unchanged() -> None:
    async with create_test_client(create_query_app()) as client:
        response = await client.get("/query", params=[("name", "alice"), ("tag", "one"), ("tag", "two")])

    assert response.status_code == 200
    assert response.json() == {
        "query": [["name", "alice"], ["tag", "one"], ["tag", "two"]],
        "decoded": None,
    }


@pytest.mark.asyncio
async def test_valid_encoded_param_replaces_original_query() -> None:
    encoded = encode_query_param({"name": "张三", "tag": ["one", "two"]})

    async with create_test_client(create_query_app()) as client:
        response = await client.get("/query", params={"f": encoded, "ignored": "value"})

    assert response.status_code == 200
    assert response.json() == {
        "query": [["name", "张三"], ["tag", "one"], ["tag", "two"]],
        "decoded": {"name": "张三", "tag": ["one", "two"]},
    }


@pytest.mark.asyncio
async def test_nested_payload_is_preserved_in_request_state() -> None:
    encoded = encode_query_param({"query": {"title": "嵌套内容"}})

    async with create_test_client(create_query_app()) as client:
        response = await client.get("/query", params={"f": encoded})

    assert response.status_code == 200
    assert response.json()["decoded"] == {"query": {"title": "嵌套内容"}}


@pytest.mark.parametrize(
    "encoded",
    [
        "not-base64!",
        "JTVCJTIybm90JTIyJTJDJTIyYW4lMjIlMkMlMjJvYmplY3QlMjIlNUQ",
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_non_object_payload_is_ignored(encoded: str) -> None:
    async with create_test_client(create_query_app()) as client:
        response = await client.get("/query", params={"f": encoded, "kept": "value"})

    assert response.status_code == 200
    assert response.json() == {
        "query": [["f", encoded], ["kept", "value"]],
        "decoded": None,
    }


@pytest.mark.asyncio
async def test_empty_object_clears_query_and_is_saved_in_state() -> None:
    encoded = encode_query_param({})

    async with create_test_client(create_query_app()) as client:
        response = await client.get("/query", params={"f": encoded, "ignored": "value"})

    assert response.status_code == 200
    assert response.json() == {"query": [], "decoded": {}}


@pytest.mark.asyncio
async def test_non_http_scope_is_passed_through() -> None:
    received_scope: Scope | None = None

    async def downstream(scope: Scope, receive, send) -> None:
        nonlocal received_scope
        received_scope = scope

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    scope: Scope = {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}, "state": {}}
    await QueryParamDecodeMiddleware(downstream)(scope, receive, send)

    assert received_scope is scope

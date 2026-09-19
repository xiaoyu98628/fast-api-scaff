"""验证出站 HTTP 驱动资源和响应大小限制。"""

import httpx2
import pytest

from app.config.http import HttpPoolSettings, HttpSettings, HttpTimeoutSettings
from app.infrastructure.http.drivers.httpx2.factory import create_httpx2_resource


@pytest.mark.asyncio
async def test_factory_creates_independent_standard_and_stream_clients() -> None:
    settings = HttpSettings(
        timeout=HttpTimeoutSettings(connect=1.0, read=2.0, write=3.0),
        pool=HttpPoolSettings(
            timeout=4.0,
            max_connections=11,
            max_keepalive_connections=5,
            keepalive_expiry=20.0,
        ),
        stream_pool=HttpPoolSettings(
            timeout=8.0,
            max_connections=7,
            max_keepalive_connections=2,
            keepalive_expiry=15.0,
        ),
        max_response_bytes=4096,
        _env_file=None,
    )

    resource = create_httpx2_resource(settings)

    try:
        standard_client = resource._standard_client
        stream_client = resource._stream_client

        assert isinstance(standard_client, httpx2.AsyncClient)
        assert isinstance(stream_client, httpx2.AsyncClient)
        assert standard_client is not stream_client
        assert standard_client.timeout.pool == 4.0
        assert stream_client.timeout.pool == 8.0
        assert resource.standard_runtime.limit == 11
        assert resource.stream_runtime.limit == 7
        assert resource.standard_runtime.warning_ratio == 0.8
        assert resource._max_response_bytes == 4096
    finally:
        await resource.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("redirect", [False, True])
async def test_factory_does_not_share_response_cookies(monkeypatch: pytest.MonkeyPatch, stream: bool, redirect: bool) -> None:
    from functools import partial

    from app.infrastructure.http.contracts.request import HttpRequest

    received: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        received.append(request.headers.get("cookie"))
        if redirect and request.url.path == "/profile":
            return httpx2.Response(302, headers={"set-cookie": "session=caller-a; Path=/", "location": "/redirected"})
        return httpx2.Response(200, headers={"set-cookie": "session=caller-a; Path=/"})

    monkeypatch.setattr(httpx2, "AsyncClient", partial(httpx2.AsyncClient, transport=httpx2.MockTransport(handler)))
    resource = create_httpx2_resource(HttpSettings(follow_redirects=True, _env_file=None))
    try:
        for headers in ({}, {}, {"cookie": "session=explicit"}, {}):
            request = HttpRequest(method="GET", url="https://example.com/profile", headers=headers)
            if stream:
                async with resource.stream(request):
                    pass
            else:
                await resource.request(request)
    finally:
        await resource.aclose()
    # HTTPX2 跨重定向重新构建 Cookie 头，显式 Cookie 仅用于原始请求。
    expected = [None, None, "session=explicit", None]
    if redirect:
        expected = [value for original in expected for value in (original, None)]
    assert received == expected

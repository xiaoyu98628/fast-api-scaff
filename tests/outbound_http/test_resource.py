import httpx
import pytest

from app.config.http import HttpPoolSettings, HttpSettings, HttpTimeoutSettings
from app.infrastructure.http.drivers.httpx.factory import create_httpx_resource


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

    resource = create_httpx_resource(settings)

    try:
        standard_client = resource._standard_client
        stream_client = resource._stream_client

        assert isinstance(standard_client, httpx.AsyncClient)
        assert isinstance(stream_client, httpx.AsyncClient)
        assert standard_client is not stream_client
        assert standard_client.timeout.pool == 4.0
        assert stream_client.timeout.pool == 8.0
        assert resource.standard_runtime.limit == 11
        assert resource.stream_runtime.limit == 7
        assert resource.standard_runtime.warning_ratio == 0.8
        assert resource._max_response_bytes == 4096
    finally:
        await resource.aclose()

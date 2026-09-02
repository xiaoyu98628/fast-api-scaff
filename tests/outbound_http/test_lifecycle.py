import pytest

import app.infrastructure.http.manager as manager_module
from app.config.http import HttpSettings
from app.infrastructure.http.manager import HttpClientManager


@pytest.mark.asyncio
async def test_closing_uninitialized_manager_does_not_create_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    created = False

    def create(_settings: HttpSettings) -> object:
        nonlocal created
        created = True
        return object()

    monkeypatch.setattr(manager_module, "create_httpx_resource", create)
    manager = HttpClientManager(HttpSettings(_env_file=None))

    await manager.aclose()

    assert created is False

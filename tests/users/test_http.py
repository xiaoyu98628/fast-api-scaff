from uuid import uuid7

import pytest
from httpx import ASGITransport, AsyncClient

import app.interfaces.http.shared.response.codes.builder as response_code_builder_module
from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user_management.infrastructure.persistence.model import UserRecord


@pytest.fixture(autouse=True)
def reset_response_code_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(response_code_builder_module, "_response_code_builder", None)


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(service_code="321", _env_file=None),
        database=DatabaseSettings(
            default="main",
            connections={"main": {"driver": "sqlite", "database": ":memory:"}},
            _env_file=None,
        ),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


@pytest.mark.asyncio
async def test_user_http_crud_and_conflict_responses() -> None:
    app = create_app(build_settings())

    async with app.router.lifespan_context(app):
        engine = await app.state.container.databases.get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(UserRecord.metadata.create_all)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/v1/users",
                json={
                    "username": "Alice_01",
                    "email": "Alice@Example.com",
                    "display_name": "Alice",
                },
            )
            assert create_response.status_code == 201
            created = create_response.json()["data"]
            assert created["username"] == "alice_01"
            assert created["email"] == "alice@example.com"

            duplicate_response = await client.post(
                "/api/v1/users",
                json={
                    "username": "alice_01",
                    "email": "other@example.com",
                    "display_name": "Other",
                },
            )
            assert duplicate_response.status_code == 409
            assert duplicate_response.json()["code"] == "4093211002"

            user_id = created["id"]
            get_response = await client.get(f"/api/v1/users/{user_id}")
            assert get_response.status_code == 200
            assert get_response.json()["data"] == created

            list_response = await client.get("/api/v1/users", params={"offset": 0, "limit": 20})
            assert list_response.status_code == 200
            assert list_response.json()["data"]["total"] == 1

            update_response = await client.put(
                f"/api/v1/users/{user_id}",
                json={
                    "username": "alice_new",
                    "email": "new@example.com",
                    "display_name": "Alice New",
                    "status": "disabled",
                },
            )
            assert update_response.status_code == 200
            assert update_response.json()["data"]["status"] == "disabled"

            delete_response = await client.delete(f"/api/v1/users/{user_id}")
            assert delete_response.status_code == 204
            assert delete_response.content == b""

            missing_response = await client.get(f"/api/v1/users/{uuid7()}")
            assert missing_response.status_code == 404
            assert missing_response.json()["code"] == "4043211001"

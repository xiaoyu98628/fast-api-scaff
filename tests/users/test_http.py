from datetime import datetime
from uuid import UUID, uuid7

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user.infrastructure.persistence.models.user import UserModel


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


async def assert_user_status_contract(client: AsyncClient, *, user_id: str, created: dict[str, object]) -> None:
    update_with_status_response = await client.put(
        f"/api/v1/users/{user_id}",
        json={
            "username": "alice_new",
            "email": "new@example.com",
            "display_name": "Alice New",
            "status": "disabled",
        },
    )
    assert update_with_status_response.status_code == 422

    status_response = await client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"status": "disabled"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["status"] == "disabled"
    assert status_response.json()["data"]["username"] == "alice_new"
    assert status_response.json()["data"]["created_at"] == created["created_at"]

    invalid_status_response = await client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"status": "unknown"},
    )
    assert invalid_status_response.status_code == 422

    missing_status_response = await client.patch(
        f"/api/v1/users/{uuid7()}/status",
        json={"status": "active"},
    )
    assert missing_status_response.status_code == 404


@pytest.mark.asyncio
async def test_user_http_crud_and_conflict_responses() -> None:
    app = create_app(build_settings())

    async with app.router.lifespan_context(app):
        engine = await app.state.container.databases.get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(UserModel.metadata.create_all)

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
            assert datetime.fromisoformat(created["created_at"]).tzinfo is None
            assert datetime.fromisoformat(created["updated_at"]).tzinfo is None

            async with app.state.container.databases.session() as session:
                stored_created_at = await session.scalar(select(UserModel.created_at).where(UserModel.id == UUID(created["id"])))

            assert stored_created_at == datetime.fromisoformat(created["created_at"])

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

            list_response = await client.get("/api/v1/users", params={"page": 1, "limit": 1000})
            assert list_response.status_code == 200
            list_data = list_response.json()["data"]
            assert list_data["meta"] == {
                "page": 1,
                "limit": 1000,
                "total": 1,
                "total_pages": 1,
            }
            assert "total" not in list_data
            assert "page" not in list_data
            assert "limit" not in list_data
            assert "offset" not in list_data
            assert "page_size" not in list_data
            assert list_data["items"][0]["created_at"] == created["created_at"]

            legacy_list_response = await client.get(
                "/api/v1/users",
                params={"page": 1, "page_size": 20},
            )
            assert legacy_list_response.status_code == 422

            for invalid_params in (
                {"page": 0, "limit": 20},
                {"page": 1, "limit": 0},
                {"page": 1, "limit": 1001},
            ):
                invalid_list_response = await client.get(
                    "/api/v1/users",
                    params=invalid_params,
                )
                assert invalid_list_response.status_code == 422

            update_response = await client.put(
                f"/api/v1/users/{user_id}",
                json={
                    "username": "alice_new",
                    "email": "new@example.com",
                    "display_name": "Alice New",
                },
            )
            assert update_response.status_code == 200
            assert update_response.json()["data"]["status"] == "active"
            assert update_response.json()["data"]["created_at"] == created["created_at"]
            assert datetime.fromisoformat(update_response.json()["data"]["updated_at"]).tzinfo is None

            await assert_user_status_contract(client, user_id=user_id, created=created)

            delete_response = await client.delete(f"/api/v1/users/{user_id}")
            assert delete_response.status_code == 204
            assert delete_response.content == b""

            missing_response = await client.get(f"/api/v1/users/{uuid7()}")
            assert missing_response.status_code == 404
            assert missing_response.json()["code"] == "4043211001"

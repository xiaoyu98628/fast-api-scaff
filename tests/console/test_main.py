import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import typer
from typer.testing import CliRunner

from app.bootstrap.container import ApplicationContainer
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.composition import UserContext
from app.contexts.user.domain.values import UserStatus
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.main import create_console

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class FakeUserService:
    def __init__(self) -> None:
        self.users: list[UserDTO] = []

    async def create(self, command: CreateUserCommand) -> UserDTO:
        user = UserDTO(
            id=_USER_ID,
            username=command.username,
            email=command.email,
            display_name=command.display_name,
            status=UserStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.users.append(user)
        return user

    async def list(self, *, offset: int, limit: int) -> UserPageDTO:
        return UserPageDTO(
            items=tuple(self.users[offset : offset + limit]),
            total=len(self.users),
            offset=offset,
            limit=limit,
        )


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(name="console-test", version="1.2.3", env="testing", timezone="Asia/Shanghai", _env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def build_console(service: FakeUserService) -> tuple[CliRunner, typer.Typer]:
    settings = build_settings()

    def build_container(_settings: Settings) -> ApplicationContainer:
        databases = DatabaseManager(settings.database)
        return ApplicationContainer(
            databases=databases,
            caches=CacheManager(settings.cache),
            users=UserContext(service=cast(UserApplicationService, service)),
            async_shutdown_callbacks=(databases.aclose,),
        )

    console = ConsoleApplication(
        settings_loader=lambda: settings,
        container_builder=build_container,
    )
    return CliRunner(), create_console(console)


def test_app_info_displays_runtime_configuration() -> None:
    runner, application = build_console(FakeUserService())

    result = runner.invoke(application, ["app", "info"])

    assert result.exit_code == 0
    assert "name: console-test" in result.stdout
    assert "version: 1.2.3" in result.stdout
    assert "environment: testing" in result.stdout
    assert "timezone: Asia/Shanghai" in result.stdout


def test_user_commands_call_application_service() -> None:
    service = FakeUserService()
    runner, application = build_console(service)

    created = runner.invoke(
        application,
        [
            "users",
            "create",
            "--username",
            "alice",
            "--email",
            "alice@example.com",
            "--display-name",
            "Alice",
        ],
    )
    listed = runner.invoke(application, ["users", "list", "--offset", "0", "--limit", "10"])

    assert created.exit_code == 0
    assert json.loads(created.stdout) == {
        "id": str(_USER_ID),
        "username": "alice",
        "email": "alice@example.com",
        "display_name": "Alice",
        "status": "active",
        "created_at": _NOW.isoformat(),
        "updated_at": _NOW.isoformat(),
    }
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["items"] == [json.loads(created.stdout)]

import json
from datetime import datetime
from typing import cast
from uuid import UUID

import pytest
import typer
from pydantic import ValidationError
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
from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.values import UserStatus
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.main import create_console, run_console
from app.interfaces.console.presentation import ConsolePresenter

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 30, 20, 0)


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


class RejectingUserService(FakeUserService):
    async def create(self, command: CreateUserCommand) -> UserDTO:
        del command
        raise InvalidUserDataError("测试用户数据不合法")


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(name="console-test", version="1.2.3", env="testing", _env_file=None),
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
    settings = build_settings()

    def reject_container_build(_settings: Settings) -> ApplicationContainer:
        raise AssertionError("app info 不应构建应用容器")

    console = ConsoleApplication(
        settings_loader=lambda: settings,
        container_builder=reject_container_build,
    )
    runner = CliRunner()
    application = create_console(console)

    result = runner.invoke(application, ["app", "info"])

    assert result.exit_code == 0
    body = json.loads(result.stdout)
    timezone = body.pop("timezone")
    assert body == {
        "name": "console-test",
        "version": "1.2.3",
        "environment": "testing",
        "debug": False,
        "database_connections": [],
        "cache_connections": [],
    }
    assert timezone


def test_root_help_and_version_use_runtime_application_metadata() -> None:
    runner, application = build_console(FakeUserService())

    help_result = runner.invoke(application, ["--help"])
    version_result = runner.invoke(application, ["--version"])

    assert help_result.exit_code == 0
    assert "应用命令行入口。" in help_result.stdout
    assert "--version" in help_result.stdout
    assert "fast-api-scaff" not in help_result.stdout
    assert version_result.exit_code == 0
    assert version_result.stdout.strip() == "console-test 1.2.3"


def test_user_command_help_describes_available_operations() -> None:
    runner, application = build_console(FakeUserService())

    result = runner.invoke(application, ["users", "--help"])

    assert result.exit_code == 0
    assert "create" in result.stdout
    assert "创建用户。" in result.stdout
    assert "list" in result.stdout
    assert "分页查询用户。" in result.stdout


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

    expected_time = _NOW.isoformat()

    assert created.exit_code == 0
    assert json.loads(created.stdout) == {
        "id": str(_USER_ID),
        "username": "alice",
        "email": "alice@example.com",
        "display_name": "Alice",
        "status": "active",
        "created_at": expected_time,
        "updated_at": expected_time,
    }
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["items"] == [json.loads(created.stdout)]


def test_user_business_error_and_usage_error_use_distinct_exit_codes() -> None:
    runner, application = build_console(RejectingUserService())

    business_error = runner.invoke(
        application,
        [
            "users",
            "create",
            "--username",
            "x",
            "--email",
            "bad",
            "--display-name",
            "x",
        ],
    )
    usage_error = runner.invoke(application, ["users", "list", "--limit", "0"])

    assert business_error.exit_code == ConsoleExitCode.FAILURE
    assert business_error.stdout == ""
    assert business_error.stderr.strip() == "Error: 测试用户数据不合法"
    assert usage_error.exit_code == ConsoleExitCode.USAGE


def test_run_console_renders_expected_configuration_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValidationError) as captured_error:
        AppSettings(service_code="invalid", _env_file=None)

    def fail() -> None:
        raise captured_error.value

    with pytest.raises(SystemExit) as exit_error:
        run_console(fail, ConsolePresenter())

    output = capsys.readouterr()
    assert exit_error.value.code == ConsoleExitCode.FAILURE
    assert output.out == ""
    assert "Error: 配置 service_code：" in output.err
    assert "Traceback" not in output.err


def test_run_console_preserves_unexpected_programming_error() -> None:
    def fail() -> None:
        raise RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        run_console(fail, ConsolePresenter())

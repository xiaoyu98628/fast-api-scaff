"""验证 Console 进程入口、退出码和标准流契约。"""

import json
import logging
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from typing import cast
from uuid import UUID

import pytest
import typer
from click import unstyle
from pydantic import ValidationError
from typer.testing import CliRunner

from app.bootstrap.console.application import ConsoleHost
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.http import HttpSettings
from app.config.logging import LoggingSettings
from app.config.queue import QueueSettings
from app.config.settings import Settings
from app.config.vector import VectorSettings
from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.composition import build_user_context
from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.values import UserStatus
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.http.errors import HttpTransportError
from app.infrastructure.http.manager import HttpClientManager
from app.infrastructure.logging.context import RuntimeContextFilter
from app.infrastructure.queue.manager import QueueManager
from app.infrastructure.vector.manager import VectorStoreManager
from app.interfaces.console.cli import create_console, run_console
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter
from app.runtime.container import ApplicationContainer

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 30, 20, 0)


class FakeUserService:
    def __init__(self) -> None:
        self.users: list[UserDTO] = []
        self.passwords: list[str] = []

    async def create(self, command: CreateUserCommand) -> UserDTO:
        self.passwords.append(command.password)
        user = UserDTO(
            id=_USER_ID,
            username=command.username,
            email=command.email,
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
        caches = CacheManager(settings.cache)
        http = HttpClientManager(HttpSettings(_env_file=None))
        vectors = VectorStoreManager(VectorSettings(_env_file=None))
        return ApplicationContainer(
            queues=QueueManager(QueueSettings(_env_file=None), databases),
            databases=databases,
            caches=caches,
            http=http,
            vectors=vectors,
            users=replace(build_user_context(databases), service=cast(UserApplicationService, service)),
            async_shutdown_callbacks=(databases.aclose, caches.aclose, http.aclose, vectors.aclose),
        )

    console = ConsoleHost(
        settings,
        container_builder=build_container,
    )
    return CliRunner(), create_console(console)


def test_app_info_displays_runtime_configuration() -> None:
    settings = build_settings().model_copy(
        update={
            "queue": QueueSettings(
                _env_file=None,
                connections={"events": {"driver": "redis", "host": "localhost"}},
            )
        }
    )

    def reject_container_build(_settings: Settings) -> ApplicationContainer:
        raise AssertionError("app info 不应构建应用容器")

    console = ConsoleHost(
        settings,
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
        "queue_connections": ["events"],
        "vector_connections": [],
    }
    assert timezone


def test_root_help_and_version_use_runtime_application_metadata() -> None:
    runner, application = build_console(FakeUserService())

    help_result = runner.invoke(application, ["--help"])
    version_result = runner.invoke(application, ["--version"])
    help_output = unstyle(help_result.stdout)

    assert help_result.exit_code == 0
    assert "应用命令行入口。" in help_output
    assert "--version" in help_output
    assert "fast-api-scaff" not in help_output
    assert version_result.exit_code == 0
    assert version_result.stdout.strip() == "console-test 1.2.3"


def test_user_command_help_describes_available_operations() -> None:
    runner, application = build_console(FakeUserService())

    result = runner.invoke(application, ["users", "--help"])
    output = unstyle(result.stdout)

    assert result.exit_code == 0
    assert "create" in output
    assert "创建用户。" in output
    assert "list" in output
    assert "分页查询用户。" in output


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
            "--password",
            "password123",
        ],
    )
    listed = runner.invoke(application, ["users", "list", "--page", "1", "--limit", "1000"])

    expected_time = _NOW.isoformat()

    assert created.exit_code == 0
    assert json.loads(created.stdout) == {
        "id": str(_USER_ID),
        "username": "alice",
        "email": "alice@example.com",
        "status": "active",
        "created_at": expected_time,
        "updated_at": expected_time,
    }
    assert service.passwords == ["password123"]
    assert listed.exit_code == 0
    assert json.loads(listed.stdout) == {
        "items": [json.loads(created.stdout)],
        "total": 1,
        "offset": 0,
        "limit": 1000,
    }


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
            "--password",
            "password123",
        ],
    )
    invalid_page = runner.invoke(application, ["users", "list", "--page", "0"])
    invalid_limit = runner.invoke(application, ["users", "list", "--limit", "0"])
    excessive_limit = runner.invoke(application, ["users", "list", "--limit", "1001"])
    legacy_offset_error = runner.invoke(application, ["users", "list", "--offset", "0"])
    legacy_page_size_error = runner.invoke(application, ["users", "list", "--page-size", "20"])

    assert business_error.exit_code == ConsoleExitCode.FAILURE
    assert business_error.stdout == ""
    assert business_error.stderr.strip() == "Error: 测试用户数据不合法"
    assert invalid_page.exit_code == ConsoleExitCode.USAGE
    assert invalid_limit.exit_code == ConsoleExitCode.USAGE
    assert excessive_limit.exit_code == ConsoleExitCode.USAGE
    assert legacy_offset_error.exit_code == ConsoleExitCode.USAGE
    assert legacy_page_size_error.exit_code == ConsoleExitCode.USAGE


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


def test_run_console_renders_outbound_http_error(capsys: pytest.CaptureFixture[str]) -> None:
    def fail() -> None:
        raise HttpTransportError("上游服务不可用")

    with pytest.raises(SystemExit) as exit_error:
        run_console(fail, ConsolePresenter())

    output = capsys.readouterr()
    assert exit_error.value.code == ConsoleExitCode.FAILURE
    assert output.out == ""
    assert output.err.strip() == "Error: 上游服务不可用"


def test_run_console_preserves_unexpected_programming_error() -> None:
    def fail() -> None:
        raise RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        run_console(fail, ConsolePresenter())


def test_run_console_binds_command_id_without_leaking(caplog: pytest.LogCaptureFixture) -> None:
    command_id = "00000000000040008000000000000002"
    logger = logging.getLogger("app.test.console.context")
    runtime_filter = RuntimeContextFilter()
    caplog.handler.addFilter(runtime_filter)
    caplog.set_level(logging.INFO)

    try:
        run_console(
            lambda: logger.info("inside command"),
            ConsolePresenter(),
            command_id_factory=lambda: command_id,
        )
        logger.info("outside command")
    finally:
        caplog.handler.removeFilter(runtime_filter)

    inside = next(record for record in caplog.records if record.getMessage() == "inside command")
    outside = next(record for record in caplog.records if record.getMessage() == "outside command")
    assert getattr(inside, "command_id", None) == command_id
    assert getattr(inside, "correlation_id", None) == command_id
    assert getattr(outside, "command_id", None) is None
    assert getattr(outside, "correlation_id", None) is None


@pytest.mark.parametrize(("name", "value"), [("HTTP_POOL__MAX_CONNECTIONS", "0"), ("LOG_LEVEL", "invalid")])
@pytest.mark.parametrize("color", [False, True], ids=["plain", "colored"])
def test_console_help_loads_and_validates_environment(name: str, value: str, color: bool) -> None:
    color_variables = {"NO_COLOR", "FORCE_COLOR", "PY_COLORS", "GITHUB_ACTIONS", "_TYPER_FORCE_DISABLE_TERMINAL"}
    environment = {key: item for key, item in os.environ.items() if key not in color_variables}
    environment["TERM"] = "xterm-256color" if color else "dumb"
    if color:
        environment["GITHUB_ACTIONS"] = "true"
    else:
        environment["NO_COLOR"] = "1"
    environment[name] = value
    result = subprocess.run(
        [sys.executable, "-m", "app.console", "--help"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ValidationError" in result.stderr


@pytest.mark.parametrize(
    ("name", "value", "location"), [("HTTP_POOL__MAX_CONNECTIONS", "0", "pool.max_connections"), ("LOG_LEVEL", "invalid", "level")]
)
def test_console_configuration_failure_matches_eager_host_startup(name: str, value: str, location: str) -> None:
    prefixes = ("APP_", "DB_", "CACHE_", "HTTP_", "CORS_", "LOG_")
    environment = {key: item for key, item in os.environ.items() if not key.startswith(prefixes)}
    environment[name] = value
    script = """
from app.config.settings import Settings
for field in Settings.model_fields.values():
    field.annotation.model_config["env_file"] = None
from app.console import main
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, "app", "info"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert location in result.stderr
    assert "ValidationError" in result.stderr


def test_settings_accept_explicit_overrides_in_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    http = HttpSettings(_env_file=None)
    logging = LoggingSettings(_env_file=None)
    monkeypatch.setenv("HTTP_POOL__MAX_CONNECTIONS", "0")
    monkeypatch.setenv("LOG_LEVEL", "invalid")
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
        http=http,
        logging=logging,
    )
    assert settings.http is http
    assert settings.logging is logging
    with pytest.raises(ValidationError):
        Settings(app=settings.app, database=settings.database, cache=settings.cache, cors=settings.cors)

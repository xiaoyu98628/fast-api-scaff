"""验证 Console 命令注册、发现和冲突处理。"""

from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import typer

from app.bootstrap.build import build_application_container
from app.bootstrap.console.application import ConsoleHost
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.errors import QueueError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.commands.queue import list_failures
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.discovery import discover_console_commands
from app.interfaces.console.registry import ConsoleCommandRegistry
from tests.console.test_application import build_settings


class FirstCommand(ConsoleCommand):
    group = "testing"
    group_help = "测试命令。"
    name = "first"
    help = "第一个测试命令。"

    def handle(self) -> None:
        pass


class DuplicateCommand(FirstCommand):
    pass


class ConflictingGroupHelpCommand(FirstCommand):
    group_help = "不一致的测试命令说明。"
    name = "second"


@pytest.mark.asyncio
async def test_console_rejects_unconfigured_failure_database() -> None:
    settings = build_settings()
    container = build_application_container(settings)
    try:
        with pytest.raises(QueueError, match="SQL 失败存储数据库未配置"):
            await list_failures(
                ConsoleContext(settings, container, command_id="command-123"),
                limit=20,
                offset=0,
            )
    finally:
        await container.aclose()


@pytest.mark.asyncio
async def test_list_failures_includes_safe_diagnostics_without_payload() -> None:
    failure_id = uuid4()
    job_id = uuid4()
    failed_at = datetime.now()
    stacktrace = ({"module": "tests.jobs", "function": "ExampleJob.handle", "line": 27},)
    record = FailedJobRecord(
        failure_id=failure_id,
        payload=b"sensitive task data",
        connection="main",
        queue="jobs",
        failed_at=failed_at,
        attempts=1,
        reason="handler_error",
        job_id=job_id,
        error_type="builtins.ValueError",
        stacktrace=stacktrace,
    )
    failed_jobs = Mock()
    failed_jobs.list = AsyncMock(return_value=[record])
    context = cast(ConsoleContext, Mock(container=Mock(queues=Mock(failed_jobs=failed_jobs))))

    result = await list_failures(context, limit=20, offset=0)

    assert result == [
        {
            "failure_id": failure_id,
            "job_id": job_id,
            "connection": "main",
            "queue": "jobs",
            "failed_at": failed_at,
            "attempts": 1,
            "reason": "handler_error",
            "error_type": "builtins.ValueError",
            "stacktrace": stacktrace,
        }
    ]
    assert "sensitive task data" not in repr(result)


def test_discovery_finds_concrete_commands_in_stable_order() -> None:
    commands = discover_console_commands(ConsoleHost(build_settings()))

    assert [(command.group, command.name) for command in commands] == [
        ("app", "info"),
        ("queue", "failed"),
        ("queue", "forget"),
        ("queue", "retry"),
        ("users", "create"),
        ("users", "list"),
    ]


def test_registry_rejects_duplicate_command() -> None:
    registry = ConsoleCommandRegistry(typer.Typer())
    console = ConsoleHost(build_settings())
    registry.register(FirstCommand(console))

    try:
        registry.register(DuplicateCommand(console))
    except RuntimeError as error:
        assert str(error) == "Console 命令重复：testing first"
    else:
        raise AssertionError("重复 Console 命令应当注册失败")


def test_registry_rejects_conflicting_group_help() -> None:
    registry = ConsoleCommandRegistry(typer.Typer())
    console = ConsoleHost(build_settings())
    registry.register(FirstCommand(console))

    try:
        registry.register(ConflictingGroupHelpCommand(console))
    except RuntimeError as error:
        assert str(error) == "Console 命令组 'testing' 的帮助文本不一致"
    else:
        raise AssertionError("同一 Console 命令组的帮助文本不一致时应当注册失败")

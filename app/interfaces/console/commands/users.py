import json
from dataclasses import asdict
from datetime import datetime
from functools import partial
from uuid import UUID

import typer

from app.bootstrap.container import ApplicationContainer
from app.config.settings import Settings
from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.console.application import ConsoleApplication


async def create_user(
    container: ApplicationContainer,
    _settings: Settings,
    *,
    username: str,
    email: str,
    display_name: str,
) -> UserDTO:
    return await container.users.service.create(
        CreateUserCommand(
            username=username,
            email=email,
            display_name=display_name,
        )
    )


async def list_users(
    container: ApplicationContainer,
    _settings: Settings,
    *,
    offset: int,
    limit: int,
) -> UserPageDTO:
    return await container.users.service.list(offset=offset, limit=limit)


def _echo_json(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, default=_json_default))


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"{type(value).__name__} 不能序列化为 JSON")


def _exit_for_user_error(error: UserApplicationError | UserDomainError) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=2) from None


def build_user_commands(console: ConsoleApplication) -> typer.Typer:
    commands = typer.Typer(help="执行用户管理用例。")

    @commands.command("create")
    def create(
        username: str = typer.Option(..., help="用户名。"),
        email: str = typer.Option(..., help="邮箱地址。"),
        display_name: str = typer.Option(..., help="显示名称。"),
    ) -> None:
        try:
            user = console.run(partial(create_user, username=username, email=email, display_name=display_name))
        except (UserApplicationError, UserDomainError) as error:
            _exit_for_user_error(error)

        _echo_json(asdict(user))

    @commands.command("list")
    def list_command(
        offset: int = typer.Option(0, min=0, help="跳过的记录数。"),
        limit: int = typer.Option(20, min=1, max=100, help="返回的最大记录数。"),
    ) -> None:
        page = console.run(partial(list_users, offset=offset, limit=limit))
        _echo_json(
            {
                "items": [asdict(user) for user in page.items],
                "total": page.total,
                "offset": page.offset,
                "limit": page.limit,
            }
        )

    return commands

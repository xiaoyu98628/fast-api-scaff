import json
from dataclasses import asdict
from datetime import datetime
from functools import partial
from uuid import UUID

import typer

from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext


async def create_user(
    context: ConsoleContext,
    *,
    username: str,
    email: str,
    display_name: str,
) -> UserDTO:
    return await context.container.users.service.create(
        CreateUserCommand(
            username=username,
            email=email,
            display_name=display_name,
        )
    )


async def list_users(
    context: ConsoleContext,
    *,
    offset: int,
    limit: int,
) -> UserPageDTO:
    return await context.container.users.service.list(offset=offset, limit=limit)


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


class CreateUserConsoleCommand(ConsoleCommand):
    group = "users"
    group_help = "执行用户管理用例。"
    name = "create"
    help = "创建用户。"

    def handle(
        self,
        username: str = typer.Option(..., help="用户名。"),
        email: str = typer.Option(..., help="邮箱地址。"),
        display_name: str = typer.Option(..., help="显示名称。"),
    ) -> None:
        try:
            user = self._console.run(partial(create_user, username=username, email=email, display_name=display_name))
        except (UserApplicationError, UserDomainError) as error:
            _exit_for_user_error(error)

        _echo_json(asdict(user))


class ListUsersConsoleCommand(ConsoleCommand):
    group = "users"
    group_help = "执行用户管理用例。"
    name = "list"
    help = "分页查询用户。"

    def handle(
        self,
        offset: int = typer.Option(0, min=0, help="跳过的记录数。"),
        limit: int = typer.Option(20, min=1, max=100, help="返回的最大记录数。"),
    ) -> None:
        page = self._console.run(partial(list_users, offset=offset, limit=limit))
        _echo_json(
            {
                "items": [asdict(user) for user in page.items],
                "total": page.total,
                "offset": page.offset,
                "limit": page.limit,
            }
        )

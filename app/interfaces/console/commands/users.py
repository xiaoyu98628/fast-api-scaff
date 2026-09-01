from functools import partial

import typer

from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter


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


def _exit_for_user_error(presenter: ConsolePresenter, error: UserApplicationError | UserDomainError) -> None:
    presenter.error(error)
    raise typer.Exit(code=ConsoleExitCode.FAILURE) from None


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
            _exit_for_user_error(self._console.presenter, error)

        self._console.presenter.result(user)


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
        self._console.presenter.result(page)

from functools import partial

import typer

from app.contexts.user.application.dto import CreateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20


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
    page: int,
    limit: int,
) -> UserPageDTO:
    return await context.container.users.service.list(
        offset=(page - 1) * limit,
        limit=limit,
    )


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
        page: int = typer.Option(DEFAULT_PAGE, help="示例页码。"),
        limit: int = typer.Option(
            DEFAULT_LIMIT,
            help="示例每页记录数。",
        ),
    ) -> None:
        result = self._console.run(partial(list_users, page=page, limit=limit))
        self._console.presenter.result(result)

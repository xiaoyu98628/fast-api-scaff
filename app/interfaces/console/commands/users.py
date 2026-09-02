from functools import partial

import typer

from app.contexts.user.application.dto import CreateUserCommand, UserDTO
from app.contexts.user.application.errors import UserApplicationError
from app.contexts.user.domain.errors import UserDomainError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.exit_codes import ConsoleExitCode
from app.interfaces.console.presentation import ConsolePresenter
from app.interfaces.shared.pagination import (
    PageInput,
    PageMeta,
    PageOutput,
    calculate_total_pages,
)

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 1000


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
    pagination: PageInput,
) -> PageOutput[UserDTO]:
    result = await context.container.users.service.list(
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PageOutput(
        items=result.items,
        meta=PageMeta(
            page=pagination.page,
            limit=pagination.limit,
            total=result.total,
            total_pages=calculate_total_pages(
                total=result.total,
                limit=pagination.limit,
            ),
        ),
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
        page: int = typer.Option(DEFAULT_PAGE, min=1, help="页码，从 1 开始。"),
        limit: int = typer.Option(
            DEFAULT_LIMIT,
            min=1,
            max=MAX_LIMIT,
            help="每页记录数。",
        ),
    ) -> None:
        pagination = PageInput(page=page, limit=limit)
        result = self._console.run(partial(list_users, pagination=pagination))
        self._console.presenter.result(result)

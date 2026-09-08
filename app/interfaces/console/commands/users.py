"""提供创建和分页查询用户的 Console 命令。"""

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
MAX_LIMIT = 1000


async def create_user(
    context: ConsoleContext,
    *,
    username: str,
    email: str,
    password: str,
) -> UserDTO:
    """把 CLI 原始输入转换为创建用户用例命令。"""

    return await context.container.users.service.create(
        CreateUserCommand(
            username=username,
            email=email,
            password=password,
        )
    )


async def list_users(
    context: ConsoleContext,
    *,
    page: int,
    limit: int,
) -> UserPageDTO:
    """把从 1 开始的 CLI 页码转换为应用层偏移量。"""

    return await context.container.users.service.list(
        offset=(page - 1) * limit,
        limit=limit,
    )


def _exit_for_user_error(presenter: ConsolePresenter, error: UserApplicationError | UserDomainError) -> None:
    """输出预期用户错误并以稳定失败码结束当前命令。"""

    presenter.error(error)
    raise typer.Exit(code=ConsoleExitCode.FAILURE) from None


class CreateUserConsoleCommand(ConsoleCommand):
    """注册并处理 ``users create`` 命令。"""

    group = "users"
    group_help = "执行用户管理用例。"
    name = "create"
    help = "创建用户。"

    def handle(
        self,
        username: str = typer.Option(..., help="用户名。"),
        email: str = typer.Option(..., help="邮箱地址。"),
        password: str = typer.Option(
            ...,
            prompt=True,
            hide_input=True,
            confirmation_prompt=True,
            help="登录密码，交互输入时不回显。",
        ),
    ) -> None:
        """收集敏感密码输入，执行用例并输出新用户。"""

        try:
            user = self._console.run(partial(create_user, username=username, email=email, password=password))
        except (UserApplicationError, UserDomainError) as error:
            _exit_for_user_error(self._console.presenter, error)

        self._console.presenter.result(user)


class ListUsersConsoleCommand(ConsoleCommand):
    """注册并处理 ``users list`` 命令。"""

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
            help="每页记录数，范围为 1–1000。",
        ),
    ) -> None:
        """校验分页选项并输出一页用户。"""

        result = self._console.run(partial(list_users, page=page, limit=limit))
        self._console.presenter.result(result)

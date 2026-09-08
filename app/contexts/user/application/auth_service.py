"""编排登录、当前用户查询和退出登录用例。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.contexts.user.application.auth_dto import LoginCommand, TokenDTO
from app.contexts.user.application.auth_errors import AuthenticationRequiredError, InvalidCredentialsError, LoginUserNotFoundError
from app.contexts.user.application.dto import UserDTO
from app.contexts.user.application.password_hasher import PasswordHasher
from app.contexts.user.application.session_token import SessionCredential, SessionTokenCodec
from app.contexts.user.application.unit_of_work import UserUnitOfWorkFactory
from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.session import UserSession
from app.contexts.user.domain.values import Username, UserStatus


@dataclass(frozen=True, slots=True)
class AuthApplicationService:
    """编排简单数据库会话，不定义角色或接管用户 CRUD。"""

    unit_of_work_factory: UserUnitOfWorkFactory
    password_hasher: PasswordHasher
    tokens: SessionTokenCodec
    session_ttl_seconds: int
    clock: Callable[[], datetime] = datetime.now

    def __post_init__(self) -> None:
        """确保直接构造服务时也不能绕过会话有效期约束。"""

        if type(self.session_ttl_seconds) is not int or self.session_ttl_seconds <= 0:
            raise ValueError("会话有效期必须为正整数秒")

    async def login(self, command: LoginCommand) -> TokenDTO:
        """验证账户凭据，并在独立事务中创建服务器端会话。"""

        try:
            username = Username(command.username)
        except InvalidUserDataError:
            raise InvalidCredentialsError() from None

        # 首次事务只读取验证所需快照，不在密码慢哈希期间占用数据库事务。
        async with self.unit_of_work_factory() as uow:
            snapshot = await uow.users.find_by_username(username)

        if snapshot is None:
            raise LoginUserNotFoundError()

        verified = await self.password_hasher.verify(command.password, snapshot.password_hash)
        if not verified or snapshot.status is not UserStatus.ACTIVE:
            raise InvalidCredentialsError()

        # 慢哈希完成后重新核对账户，避免期间发生的禁用、改名或密码更新被忽略。
        async with self.unit_of_work_factory() as uow:
            current = await uow.users.find(snapshot.id)
            if current is None:
                raise LoginUserNotFoundError()
            if current.status is not UserStatus.ACTIVE or current.password_hash != snapshot.password_hash or current.username != snapshot.username:
                raise InvalidCredentialsError()

            # 原始 Token 只返回调用方，事务中持久化的是编解码器生成的摘要。
            credential = self.tokens.issue()
            now = self.clock()
            await uow.sessions.add(
                UserSession(
                    token_digest=self.tokens.digest(credential),
                    user_id=current.id,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=self.session_ttl_seconds),
                )
            )
            await uow.commit()

        return TokenDTO(
            access_token=credential.token,
            expires_in=self.session_ttl_seconds,
            user_id=current.id.value,
        )

    async def current_user(self, credential: SessionCredential) -> UserDTO:
        """解析有效会话，并返回仍处于启用状态的当前用户。"""

        async with self.unit_of_work_factory() as uow:
            session = await uow.sessions.find(self.tokens.digest(credential))
            if session is None or not session.is_valid(now=self.clock()):
                raise AuthenticationRequiredError()

            user = await uow.users.find(session.user_id)
            if user is None or user.status is not UserStatus.ACTIVE:
                raise AuthenticationRequiredError()

            return UserDTO.from_domain(user)

    async def logout(self, credential: SessionCredential) -> None:
        """幂等删除当前服务器端会话。"""

        async with self.unit_of_work_factory() as uow:
            await uow.sessions.remove(self.tokens.digest(credential))
            await uow.commit()

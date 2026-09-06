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
        if type(self.session_ttl_seconds) is not int or self.session_ttl_seconds <= 0:
            raise ValueError("会话有效期必须为正整数秒")

    async def login(self, command: LoginCommand) -> TokenDTO:
        try:
            username = Username(command.username)
        except InvalidUserDataError:
            raise InvalidCredentialsError() from None

        async with self.unit_of_work_factory() as uow:
            snapshot = await uow.users.find_by_username(username)

        if snapshot is None:
            raise LoginUserNotFoundError()

        verified = await self.password_hasher.verify(command.password, snapshot.password_hash)
        if not verified or snapshot.status is not UserStatus.ACTIVE:
            raise InvalidCredentialsError()

        # 慢哈希不占用数据库事务；完成后重新核对账户再签发。
        async with self.unit_of_work_factory() as uow:
            current = await uow.users.find(snapshot.id)
            if current is None:
                raise LoginUserNotFoundError()
            if current.status is not UserStatus.ACTIVE or current.password_hash != snapshot.password_hash or current.username != snapshot.username:
                raise InvalidCredentialsError()

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

        return TokenDTO(access_token=credential.token, expires_in=self.session_ttl_seconds)

    async def current_user(self, credential: SessionCredential) -> UserDTO:
        async with self.unit_of_work_factory() as uow:
            session = await uow.sessions.find(self.tokens.digest(credential))
            if session is None or not session.is_valid(now=self.clock()):
                raise AuthenticationRequiredError()

            user = await uow.users.find(session.user_id)
            if user is None or user.status is not UserStatus.ACTIVE:
                raise AuthenticationRequiredError()

            return UserDTO.from_domain(user)

    async def logout(self, credential: SessionCredential) -> None:
        async with self.unit_of_work_factory() as uow:
            await uow.sessions.remove(self.tokens.digest(credential))
            await uow.commit()

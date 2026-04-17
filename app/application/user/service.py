"""用户相关用例编排（注册、登录等）。

口令哈希统一经本服务调用 ``app.common.utils.password``，勿在 Router 或 ORM Model 中直写 bcrypt。
"""

from app.application.user.dto import LoginResult, UserSnapshot
from app.application.user.errors import UserErrorCode
from app.common.errors import BizException
from app.common.utils.jwt import create_access_token
from app.common.utils.password import verify_password
from app.infrastructure.db.session import SessionProvider
from app.infrastructure.db.repositories.user_repository import UserRepository


class UserService:
    """用户用例：实现注册/登录时在方法内使用 ``hash_password`` / ``verify_password``。"""

    def __init__(
        self,
        user_repository: UserRepository | None = None,
        session_provider: SessionProvider | None = None,
    ) -> None:
        self._users = user_repository or UserRepository()
        self._session_provider = session_provider or SessionProvider()

    async def login(
        self,
        username: str,
        password: str,
    ) -> LoginResult:
        """用户名 + 密码登录；失败时统一抛出 ``LOGIN_FAILED``（防枚举）。"""
        async with self._session_provider.session() as session:
            user = await self._users.get_active_by_username(session, username)

            if user is None or not verify_password(password, user.password):
                raise BizException(UserErrorCode.LOGIN_FAILED)

            user_snapshot = UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
            )
            access_token, expires_in = create_access_token(
                subject=user_snapshot.id,
                username=user_snapshot.username,
            )
            return LoginResult(
                user=user_snapshot,
                access_token=access_token,
                token_type="Bearer",
                expires_in=expires_in,
            )

"""用户相关用例编排（注册、登录等）。

口令哈希统一经本服务调用 ``app.common.utils.password``，勿在 Router 或 ORM Model 中直写 bcrypt。
"""

import secrets

from app.application.enums.user_status import UserStatus
from app.application.user.dto import LoginResult, PaginationMeta, UserIndexResult, UserSnapshot
from app.application.user.errors import UserErrorCode
from app.common.exceptions.biz_exception import BizException
from app.common.utils.jwt import create_access_token
from app.common.utils.password import hash_password, verify_password
from app.domain.user.entity import UserEntity
from app.infrastructure.db.session import SessionProvider
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.infrastructure.redis.token_store import AccessTokenStore


class UserService:
    """用户用例：实现注册/登录时在方法内使用 ``hash_password`` / ``verify_password``。"""

    def __init__(
        self,
        user_repository: UserRepository | None = None,
        session_provider: SessionProvider | None = None,
        access_token_store: AccessTokenStore | None = None,
    ) -> None:
        self._users = user_repository or UserRepository()
        self._session_provider = session_provider or SessionProvider()
        self._access_token_store = access_token_store or AccessTokenStore()

    async def login(
        self,
        username: str,
        password: str,
    ) -> LoginResult:
        """用户名 + 密码登录；停用账号返回明确状态错误。"""
        async with self._session_provider.session() as session:
            user = await self._users.get_active_by_username(session, username)

            if user is None or not verify_password(password, user.password):
                raise BizException(UserErrorCode.LOGIN_FAILED)
            domain_user = UserEntity(
                id=user.id,
                username=user.username,
                status=UserStatus(user.status),
            )
            if not domain_user.can_login():
                raise BizException(UserErrorCode.USER_STATUS_LOCKED)

            user_snapshot = UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                status=UserStatus(user.status),
            )
            access_token, expires_in = create_access_token(
                subject=user_snapshot.id,
                username=user_snapshot.username,
            )
            await self._access_token_store.save(access_token, expires_in)
            return LoginResult(
                user=user_snapshot,
                access_token=access_token,
                token_type="Bearer",
                expires_in=expires_in,
            )

    async def store(
        self,
        username: str,
        password: str,
        nickname: str,
    ) -> UserSnapshot:
        """新增用户；用户名已存在时抛出 ``USER_ALREADY_EXIST``。"""
        async with self._session_provider.session() as session:
            if await self._users.get_active_by_username(session, username) is not None:
                raise BizException(UserErrorCode.USER_ALREADY_EXIST)
            user = await self._users.store(
                session,
                user_id=secrets.token_hex(13),
                username=username,
                password_hash=hash_password(password),
                nickname=nickname,
            )
            await session.commit()
            return UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                status=UserStatus(user.status),
            )

    async def index(self, page: int, page_size: int) -> UserIndexResult:
        """分页用户列表（不含已软删）；``page`` / ``page_size`` 由接口层校验为正整数范围。"""
        offset = (page - 1) * page_size
        async with self._session_provider.session() as session:
            total = await self._users.count_not_deleted(session)
            rows = await self._users.index(session, offset=offset, limit=page_size)
        last_page = max(1, (total + page_size - 1) // page_size) if total else 1
        items = [
            UserSnapshot(
                id=row.id,
                username=row.username,
                nickname=row.nickname,
                status=UserStatus(row.status),
            )
            for row in rows
        ]
        meta = PaginationMeta(
            current_page=page,
            last_page=last_page,
            total=total,
            page_size=page_size,
        )
        return UserIndexResult(items=items, meta=meta)

    async def show(self, user_id: str) -> UserSnapshot:
        """按主键查询未软删用户。"""
        async with self._session_provider.session() as session:
            user = await self._users.show(session, user_id)
            if user is None:
                raise BizException(UserErrorCode.USER_NOT_EXIST)
            return UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                status=UserStatus(user.status),
            )

    async def update(
        self,
        user_id: str,
        *,
        nickname: str | None,
        password: str | None,
    ) -> UserSnapshot:
        """更新昵称或密码；至少提供一项。"""
        if nickname is None and password is None:
            raise BizException(UserErrorCode.USER_UPDATE_NO_FIELDS)
        async with self._session_provider.session() as session:
            user = await self._users.update(
                session,
                user_id,
                nickname=nickname,
                password_hash=hash_password(password) if password is not None else None,
            )
            if user is None:
                raise BizException(UserErrorCode.USER_NOT_EXIST)
            await session.commit()
            return UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                status=UserStatus(user.status),
            )

    async def update_status(self, user_id: str, *, status: UserStatus) -> UserSnapshot:
        """更新用户状态（`activation` / `locking`）。"""
        async with self._session_provider.session() as session:
            user = await self._users.update_status(session, user_id, status=status)
            if user is None:
                raise BizException(UserErrorCode.USER_NOT_EXIST)
            await session.commit()
            return UserSnapshot(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                status=UserStatus(user.status),
            )

    async def destroy(self, user_id: str) -> None:
        """软删除用户。"""
        async with self._session_provider.session() as session:
            deleted = await self._users.destroy(session, user_id)
            if not deleted:
                raise BizException(UserErrorCode.USER_NOT_EXIST)
            await session.commit()

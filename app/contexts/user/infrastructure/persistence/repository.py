"""使用 SQLAlchemy 实现用户聚合仓储协议。"""

from typing import cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, UserId, Username
from app.contexts.user.infrastructure.persistence.mapper import (
    user_password_update_values,
    user_profile_update_values,
    user_status_update_values,
    user_to_domain,
    user_to_model,
)
from app.contexts.user.infrastructure.persistence.models.user import UserModel


class SqlAlchemyUserRepository:
    """使用 SQLAlchemy 实现用户 Repository 契约。"""

    def __init__(self, session: AsyncSession) -> None:
        """绑定工作单元提供的 Session，不自行提交事务。"""

        self._session = session

    async def find(self, user_id: UserId) -> User | None:
        """按主键读取并恢复用户聚合。"""

        model = await self._session.get(UserModel, str(user_id.value))
        return user_to_domain(model) if model is not None else None

    async def find_by_username(self, username: Username) -> User | None:
        """按规范化用户名读取并恢复用户聚合。"""

        model = await self._session.scalar(select(UserModel).where(UserModel.username == username.value))
        return user_to_domain(model) if model is not None else None

    async def exists_by_username(self, username: Username, *, excluding: UserId | None = None) -> bool:
        """检查用户名是否被当前用户之外的记录占用。"""

        statement = select(UserModel.id).where(UserModel.username == username.value)
        if excluding is not None:
            statement = statement.where(UserModel.id != str(excluding.value))

        # 只选择主键并限制一行，避免为存在性判断恢复完整聚合。
        return (await self._session.scalar(statement.limit(1))) is not None

    async def exists_by_email(self, email: EmailAddress, *, excluding: UserId | None = None) -> bool:
        """检查邮箱是否被当前用户之外的记录占用。"""

        statement = select(UserModel.id).where(UserModel.email == email.value)
        if excluding is not None:
            statement = statement.where(UserModel.id != str(excluding.value))

        return (await self._session.scalar(statement.limit(1))) is not None

    async def find_page(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        """查询总数及按创建时间倒序排列的一页用户。"""

        total = await self._session.scalar(select(func.count()).select_from(UserModel))
        # ID 作为第二排序键，确保创建时间相同时分页顺序仍然稳定。
        statement = select(UserModel).order_by(UserModel.created_at.desc(), UserModel.id.desc()).offset(offset).limit(limit)
        models = (await self._session.scalars(statement)).all()

        return [user_to_domain(model) for model in models], total or 0

    async def add(self, user: User) -> None:
        """把新用户加入当前 Session，提交由工作单元负责。"""

        self._session.add(user_to_model(user))

    async def update_profile(self, user: User) -> bool:
        """按 ID 更新用户名和邮箱，不覆盖其他用例负责的字段。"""

        return await self._update(user.id, user_profile_update_values(user))

    async def change_status(self, user: User) -> bool:
        """按 ID 更新账户状态，不覆盖用户资料或密码。"""

        return await self._update(user.id, user_status_update_values(user))

    async def reset_password(self, user: User) -> bool:
        """按 ID 更新密码哈希，不覆盖用户资料或账户状态。"""

        return await self._update(user.id, user_password_update_values(user))

    async def _update(self, user_id: UserId, values: dict[str, object]) -> bool:
        """执行一个用例专属更新，并用受影响行数表示记录是否存在。"""

        statement = update(UserModel).where(UserModel.id == str(user_id.value)).values(**values).execution_options(synchronize_session=False)
        result = cast(CursorResult[tuple[object, ...]], await self._session.execute(statement))
        return result.rowcount == 1

    async def remove(self, user_id: UserId) -> bool:
        """按 ID 删除用户，并用受影响行数表示是否删除成功。"""

        statement = delete(UserModel).where(UserModel.id == str(user_id.value)).execution_options(synchronize_session=False)
        result = cast(CursorResult[tuple[object, ...]], await self._session.execute(statement))
        return result.rowcount == 1

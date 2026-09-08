"""定义用户聚合根及其状态变更规则。"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid7

from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.values import EmailAddress, PasswordHash, UserId, Username, UserStatus


@dataclass(slots=True)
class User:
    """用户限界上下文中的用户聚合根。"""

    _id: UserId
    _username: Username
    _email: EmailAddress
    _password_hash: PasswordHash = field(repr=False)
    _status: UserStatus
    _created_at: datetime
    _updated_at: datetime

    def __post_init__(self) -> None:
        """确保任意构造路径都不能绕过领域值和时间类型检查。"""

        _validate_value_types(self._id, self._username, self._email, self._password_hash, self._status)
        _validate_local_datetime(self._created_at, "创建时间")
        _validate_local_datetime(self._updated_at, "更新时间")

    @property
    def id(self) -> UserId:
        """返回用户领域 ID。"""

        return self._id

    @property
    def username(self) -> Username:
        """返回规范化后的用户名。"""

        return self._username

    @property
    def email(self) -> EmailAddress:
        """返回规范化后的邮箱地址。"""

        return self._email

    @property
    def password_hash(self) -> PasswordHash:
        """返回可持久化的密码哈希值对象。"""

        return self._password_hash

    @property
    def status(self) -> UserStatus:
        """返回当前账户状态。"""

        return self._status

    @property
    def created_at(self) -> datetime:
        """返回本地无时区创建时间。"""

        return self._created_at

    @property
    def updated_at(self) -> datetime:
        """返回本地无时区更新时间。"""

        return self._updated_at

    @classmethod
    def create(
        cls,
        *,
        username: str,
        email: str,
        password_hash: PasswordHash,
        now: datetime,
        user_id: UUID | None = None,
    ) -> User:
        """创建默认处于启用状态的新用户聚合。"""

        return cls(
            _id=UserId(user_id if user_id is not None else uuid7()),
            _username=Username(username),
            _email=EmailAddress(email),
            _password_hash=password_hash,
            _status=UserStatus.ACTIVE,
            _created_at=now,
            _updated_at=now,
        )

    @classmethod
    def rehydrate(
        cls,
        *,
        user_id: UserId,
        username: Username,
        email: EmailAddress,
        password_hash: PasswordHash,
        status: UserStatus,
        created_at: datetime,
        updated_at: datetime,
    ) -> User:
        """从持久化数据恢复聚合，同时重新检查领域不变量。"""

        return cls(
            _id=user_id,
            _username=username,
            _email=email,
            _password_hash=password_hash,
            _status=status,
            _created_at=created_at,
            _updated_at=updated_at,
        )

    def update_profile(
        self,
        *,
        username: str,
        email: str,
        now: datetime,
    ) -> None:
        """规范化并更新用户名、邮箱及更新时间。"""

        resolved_username = Username(username)
        resolved_email = EmailAddress(email)
        _validate_local_datetime(now, "更新时间")

        self._username = resolved_username
        self._email = resolved_email
        self._updated_at = now

    def change_status(self, *, status: UserStatus, now: datetime) -> None:
        """更新账户状态及更新时间。"""

        resolved_status = _validate_user_status(status)
        _validate_local_datetime(now, "更新时间")

        self._status = resolved_status
        self._updated_at = now

    def reset_password(self, *, password_hash: PasswordHash, now: datetime) -> None:
        """替换已经由应用层生成的密码哈希。"""

        if not isinstance(password_hash, PasswordHash):
            raise InvalidUserDataError("密码哈希类型不正确")

        _validate_local_datetime(now, "更新时间")
        self._password_hash = password_hash
        self._updated_at = now


def _validate_value_types(
    user_id: UserId,
    username: Username,
    email: EmailAddress,
    password_hash: PasswordHash,
    status: UserStatus,
) -> None:
    """集中检查聚合内部字段必须使用对应领域类型。"""

    if not isinstance(user_id, UserId):
        raise InvalidUserDataError("用户 ID 类型不正确")

    if not isinstance(username, Username):
        raise InvalidUserDataError("用户名类型不正确")

    if not isinstance(email, EmailAddress):
        raise InvalidUserDataError("邮箱地址类型不正确")

    if not isinstance(password_hash, PasswordHash):
        raise InvalidUserDataError("密码哈希类型不正确")

    _validate_user_status(status)


def _validate_user_status(value: UserStatus) -> UserStatus:
    """校验并返回账户状态值对象。"""

    if not isinstance(value, UserStatus):
        raise InvalidUserDataError("用户状态不正确")

    return value


def _validate_local_datetime(value: datetime, name: str) -> None:
    """校验用户时间字段采用本地无时区 datetime。"""

    if not isinstance(value, datetime):
        raise InvalidUserDataError(f"{name}必须是 datetime")

    if value.utcoffset() is not None:
        raise InvalidUserDataError(f"{name}必须使用本地无时区时间")

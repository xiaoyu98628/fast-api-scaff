from datetime import UTC, datetime

from app.contexts.user_management.domain.user import User
from app.contexts.user_management.domain.values import EmailAddress, UserId, Username, UserStatus
from app.contexts.user_management.infrastructure.persistence.model import UserRecord


def user_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id.value,
        username=user.username.value,
        email=user.email.value,
        display_name=user.display_name,
        status=user.status.value,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def user_to_domain(record: UserRecord) -> User:
    return User(
        id=UserId(record.id),
        username=Username(record.username),
        email=EmailAddress(record.email),
        display_name=record.display_name,
        status=UserStatus(record.status),
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
    )


def update_user_record(record: UserRecord, user: User) -> None:
    record.username = user.username.value
    record.email = user.email.value
    record.display_name = user.display_name
    record.status = user.status.value
    record.updated_at = user.updated_at


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)

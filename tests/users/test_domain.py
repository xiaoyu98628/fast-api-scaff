from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest

from app.contexts.user.domain.errors import InvalidUserDataError
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import Password, PasswordHash, UserId, UserStatus

_PASSWORD_HASH = PasswordHash("test-password-hash")


def test_user_creation_normalizes_identity_fields() -> None:
    now = datetime(2026, 8, 28, 18, 0)

    user = User.create(
        username="  Alice_01 ",
        email=" Alice@Example.COM ",
        password_hash=_PASSWORD_HASH,
        now=now,
    )

    assert user.username.value == "alice_01"
    assert user.email.value == "alice@example.com"
    assert user.password_hash == _PASSWORD_HASH
    assert user.status is UserStatus.ACTIVE
    assert user.created_at == now
    assert user.updated_at == now


def test_password_validates_length_without_normalizing_secret() -> None:
    password = Password("  password  ")

    assert password.value == "  password  "
    assert "password" not in repr(password)


@pytest.mark.parametrize("value", ["short", "x" * 129])
def test_password_rejects_invalid_length(value: str) -> None:
    with pytest.raises(InvalidUserDataError, match="密码长度"):
        Password(value)


def test_user_id_rejects_non_uuid_value() -> None:
    with pytest.raises(InvalidUserDataError, match="用户 ID 必须是 UUID"):
        UserId(cast(UUID, "not-a-uuid"))


def test_user_profile_update_preserves_password_status_and_creation_time() -> None:
    created_at = datetime(2026, 8, 28, 18, 0)
    updated_at = created_at + timedelta(minutes=1)
    user = User.create(username="alice", email="alice@example.com", password_hash=_PASSWORD_HASH, now=created_at)

    user.update_profile(
        username="alice_new",
        email="new@example.com",
        now=updated_at,
    )

    assert user.username.value == "alice_new"
    assert user.email.value == "new@example.com"
    assert user.password_hash == _PASSWORD_HASH
    assert user.status is UserStatus.ACTIVE
    assert user.created_at == created_at
    assert user.updated_at == updated_at


def test_user_status_change_preserves_profile_password_and_creation_time() -> None:
    created_at = datetime(2026, 8, 28, 18, 0)
    updated_at = created_at + timedelta(minutes=1)
    user = User.create(username="alice", email="alice@example.com", password_hash=_PASSWORD_HASH, now=created_at)

    user.change_status(status=UserStatus.DISABLED, now=updated_at)

    assert user.username.value == "alice"
    assert user.email.value == "alice@example.com"
    assert user.password_hash == _PASSWORD_HASH
    assert user.status is UserStatus.DISABLED
    assert user.created_at == created_at
    assert user.updated_at == updated_at


def test_invalid_profile_update_does_not_partially_change_user() -> None:
    now = datetime(2026, 8, 28, 18, 0)
    user = User.create(username="alice", email="alice@example.com", password_hash=_PASSWORD_HASH, now=now)

    with pytest.raises(InvalidUserDataError):
        user.update_profile(
            username="alice_new",
            email="invalid-email",
            now=now + timedelta(minutes=1),
        )

    assert user.username.value == "alice"
    assert user.email.value == "alice@example.com"
    assert user.password_hash == _PASSWORD_HASH
    assert user.status is UserStatus.ACTIVE
    assert user.updated_at == now


@pytest.mark.parametrize(
    ("username", "email"),
    [
        ("ab", "alice@example.com"),
        ("alice", "invalid-email"),
    ],
)
def test_user_creation_rejects_invalid_profile(username: str, email: str) -> None:
    with pytest.raises(InvalidUserDataError):
        User.create(
            username=username,
            email=email,
            password_hash=_PASSWORD_HASH,
            now=datetime(2026, 8, 28, 18, 0),
        )


def test_user_rejects_timezone_aware_business_time() -> None:
    with pytest.raises(InvalidUserDataError, match="本地无时区时间"):
        User.create(
            username="alice",
            email="alice@example.com",
            password_hash=_PASSWORD_HASH,
            now=datetime(2026, 8, 28, tzinfo=UTC),
        )


def test_user_rehydration_rechecks_domain_value_types() -> None:
    now = datetime(2026, 8, 28, 18, 0)
    user = User.create(username="alice", email="alice@example.com", password_hash=_PASSWORD_HASH, now=now)

    with pytest.raises(InvalidUserDataError, match="密码哈希类型"):
        User.rehydrate(
            user_id=user.id,
            username=user.username,
            email=user.email,
            password_hash=cast(PasswordHash, "not-a-password-hash"),
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


def test_user_fields_can_only_be_changed_through_domain_methods() -> None:
    user = User.create(
        username="alice",
        email="alice@example.com",
        password_hash=_PASSWORD_HASH,
        now=datetime(2026, 8, 28, 18, 0),
    )

    with pytest.raises(AttributeError):
        setattr(user, "password_hash", PasswordHash("changed-password-hash"))

    assert user.password_hash == _PASSWORD_HASH
    assert _PASSWORD_HASH.value not in repr(user)

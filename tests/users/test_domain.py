from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.user_management.domain.errors import InvalidUserDataError
from app.contexts.user_management.domain.user import User
from app.contexts.user_management.domain.values import UserStatus


def test_user_creation_normalizes_identity_fields() -> None:
    now = datetime(2026, 8, 28, tzinfo=UTC)

    user = User.create(
        username="  Alice_01 ",
        email=" Alice@Example.COM ",
        display_name=" Alice ",
        now=now,
    )

    assert user.username.value == "alice_01"
    assert user.email.value == "alice@example.com"
    assert user.display_name == "Alice"
    assert user.status is UserStatus.ACTIVE
    assert user.created_at == now
    assert user.updated_at == now


def test_user_profile_update_preserves_creation_time() -> None:
    created_at = datetime(2026, 8, 28, tzinfo=UTC)
    updated_at = created_at + timedelta(minutes=1)
    user = User.create(username="alice", email="alice@example.com", display_name="Alice", now=created_at)

    user.update_profile(
        username="alice_new",
        email="new@example.com",
        display_name="Alice New",
        status=UserStatus.DISABLED,
        now=updated_at,
    )

    assert user.username.value == "alice_new"
    assert user.email.value == "new@example.com"
    assert user.display_name == "Alice New"
    assert user.status is UserStatus.DISABLED
    assert user.created_at == created_at
    assert user.updated_at == updated_at


def test_invalid_profile_update_does_not_partially_change_user() -> None:
    now = datetime(2026, 8, 28, tzinfo=UTC)
    user = User.create(username="alice", email="alice@example.com", display_name="Alice", now=now)

    with pytest.raises(InvalidUserDataError):
        user.update_profile(
            username="alice_new",
            email="invalid-email",
            display_name="Alice New",
            status=UserStatus.DISABLED,
            now=now + timedelta(minutes=1),
        )

    assert user.username.value == "alice"
    assert user.email.value == "alice@example.com"
    assert user.display_name == "Alice"
    assert user.status is UserStatus.ACTIVE
    assert user.updated_at == now


@pytest.mark.parametrize(
    ("username", "email", "display_name"),
    [
        ("ab", "alice@example.com", "Alice"),
        ("alice", "invalid-email", "Alice"),
        ("alice", "alice@example.com", "   "),
    ],
)
def test_user_creation_rejects_invalid_profile(username: str, email: str, display_name: str) -> None:
    with pytest.raises(InvalidUserDataError):
        User.create(
            username=username,
            email=email,
            display_name=display_name,
            now=datetime(2026, 8, 28, tzinfo=UTC),
        )

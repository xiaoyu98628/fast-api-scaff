"""在用户领域聚合与 SQLAlchemy 模型之间显式转换。"""

from uuid import UUID

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, PasswordHash, UserId, Username, UserStatus
from app.contexts.user.infrastructure.persistence.models.user import UserModel


def user_to_model(user: User) -> UserModel:
    """把新用户聚合转换为可加入 Session 的持久化模型。"""

    return UserModel(
        id=str(user.id.value),
        username=user.username.value,
        email=user.email.value,
        password=user.password_hash.value,
        status=user.status.value,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def user_to_domain(model: UserModel) -> User:
    """把持久化模型恢复为重新检查不变量的用户聚合。"""

    return User.rehydrate(
        user_id=UserId(UUID(model.id)),
        username=Username(model.username),
        email=EmailAddress(model.email),
        password_hash=PasswordHash(model.password),
        status=UserStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def user_profile_update_values(user: User) -> dict[str, object]:
    """提取用户资料用例允许更新的字段。"""

    return {
        "username": user.username.value,
        "email": user.email.value,
        "updated_at": user.updated_at,
    }


def user_status_update_values(user: User) -> dict[str, object]:
    """提取账户状态用例允许更新的字段。"""

    return {
        "status": user.status.value,
        "updated_at": user.updated_at,
    }


def user_password_update_values(user: User) -> dict[str, object]:
    """提取密码重置用例允许更新的字段。"""

    return {
        "password": user.password_hash.value,
        "updated_at": user.updated_at,
    }

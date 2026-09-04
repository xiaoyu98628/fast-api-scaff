from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, PasswordHash, UserId, Username, UserStatus
from app.contexts.user.infrastructure.persistence.models.user import UserModel


def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id.value,
        username=user.username.value,
        email=user.email.value,
        password=user.password_hash.value,
        status=user.status.value,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def user_to_domain(model: UserModel) -> User:
    return User.rehydrate(
        user_id=UserId(model.id),
        username=Username(model.username),
        email=EmailAddress(model.email),
        password_hash=PasswordHash(model.password),
        status=UserStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def user_update_values(user: User) -> dict[str, object]:
    return {
        "username": user.username.value,
        "email": user.email.value,
        "password": user.password_hash.value,
        "status": user.status.value,
        "updated_at": user.updated_at,
    }

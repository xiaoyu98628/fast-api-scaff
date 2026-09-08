from dataclasses import dataclass, field
from uuid import UUID

from app.contexts.user.application.auth_errors import InvalidCredentialsError


@dataclass(frozen=True, slots=True)
class LoginCommand:
    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.username, str) or not 1 <= len(self.username) <= 128:
            raise InvalidCredentialsError()
        if not isinstance(self.password, str) or not 1 <= len(self.password) <= 1024:
            raise InvalidCredentialsError()


@dataclass(frozen=True, slots=True)
class TokenDTO:
    access_token: str = field(repr=False)
    expires_in: int
    user_id: UUID
    token_type: str = "bearer"

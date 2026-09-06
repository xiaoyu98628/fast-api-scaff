import re
from dataclasses import dataclass, field
from typing import Protocol

from app.contexts.user.application.auth_errors import AuthenticationRequiredError


@dataclass(frozen=True, slots=True)
class SessionCredential:
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", self.token) is None:
            raise AuthenticationRequiredError()


class SessionTokenCodec(Protocol):
    def issue(self) -> SessionCredential: ...

    def digest(self, credential: SessionCredential) -> str: ...

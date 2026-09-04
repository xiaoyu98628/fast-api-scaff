from pwdlib import PasswordHash as PwdlibPasswordHash

from app.contexts.user.domain.values import Password
from app.contexts.user.infrastructure.security.password_hasher import PwdlibPasswordHasher


def test_pwdlib_password_hasher_generates_verifiable_non_plaintext_hash() -> None:
    plaintext = "correct-horse-battery-staple"

    password_hash = PwdlibPasswordHasher().hash(Password(plaintext))

    assert password_hash.value != plaintext
    assert password_hash.value.startswith("$argon2")
    assert PwdlibPasswordHash.recommended().verify(plaintext, password_hash.value) is True

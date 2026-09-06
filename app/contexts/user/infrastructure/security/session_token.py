import hashlib
import secrets

from app.contexts.user.application.session_token import SessionCredential


class SecureSessionTokenCodec:
    def issue(self) -> SessionCredential:
        return SessionCredential(token=secrets.token_urlsafe(32))

    def digest(self, credential: SessionCredential) -> str:
        return hashlib.sha256(credential.token.encode("utf-8")).hexdigest()

"""使用安全随机数和 SHA-256 实现会话令牌协议。"""

import hashlib
import secrets

from app.contexts.user.application.session_token import SessionCredential


class SecureSessionTokenCodec:
    """签发 URL-safe 原始令牌，并生成固定长度持久化摘要。"""

    def issue(self) -> SessionCredential:
        """使用 32 字节系统安全随机数签发会话凭据。"""

        return SessionCredential(token=secrets.token_urlsafe(32))

    def digest(self, credential: SessionCredential) -> str:
        """生成 64 位小写十六进制 SHA-256 摘要。"""

        return hashlib.sha256(credential.token.encode("utf-8")).hexdigest()

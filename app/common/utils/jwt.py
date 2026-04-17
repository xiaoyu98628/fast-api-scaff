"""JWT 工具：签发与校验访问令牌。"""

from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from config.config import get_config


def create_access_token(
    *,
    subject: str,
    username: str,
) -> tuple[str, int]:
    """签发访问令牌，返回 ``(token, expires_in_seconds)``。"""
    jwt_config = get_config().jwt
    expire_delta = timedelta(minutes=jwt_config.access_token_expire_minutes)
    expires_at = datetime.now(UTC) + expire_delta
    payload = {
        "sub": subject,
        "username": username,
        "exp": expires_at,
    }
    token = jwt.encode(payload, jwt_config.secret_key, algorithm=jwt_config.algorithm)
    return token, int(expire_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    """校验访问令牌并返回 payload。"""
    jwt_config = get_config().jwt
    return jwt.decode(token, jwt_config.secret_key, algorithms=[jwt_config.algorithm])


def is_access_token_valid(token: str) -> bool:
    """便捷校验：合法返回 ``True``，否则 ``False``。"""
    try:
        decode_access_token(token)
        return True
    except InvalidTokenError:
        return False

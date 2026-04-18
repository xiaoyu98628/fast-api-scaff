"""JWT 签发与校验。"""

from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from config.config import get_config


def create_access_token(
    *,
    subject: str,
    username: str,
) -> tuple[str, int]:
    jwt_setting = get_config().jwt
    expire_delta = timedelta(minutes=jwt_setting.access_token_expire_minutes)
    expires_at = datetime.now(UTC) + expire_delta
    payload = {
        "sub": subject,
        "username": username,
        "exp": expires_at,
    }
    token = jwt.encode(payload, jwt_setting.secret_key, algorithm=jwt_setting.algorithm)
    return token, int(expire_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    jwt_setting = get_config().jwt
    return jwt.decode(token, jwt_setting.secret_key, algorithms=[jwt_setting.algorithm])


def is_access_token_valid(token: str) -> bool:
    try:
        decode_access_token(token)
        return True
    except InvalidTokenError:
        return False

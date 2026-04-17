"""口令哈希（bcrypt），用于注册存库与登录校验；非对称加密请走其他方案。"""

import bcrypt


def hash_password(password: str) -> str:
    """将明文密码加密为哈希字符串（自动生成盐）。"""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否与哈希匹配。"""
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(plain_bytes, hashed_bytes)
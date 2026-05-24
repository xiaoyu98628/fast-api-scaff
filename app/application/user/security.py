import hashlib


def hash_password(password: str) -> str:
    """密码哈希（脚手架实现，生产环境请换用 bcrypt/argon2）。"""
    return hashlib.sha256(password.encode()).hexdigest()

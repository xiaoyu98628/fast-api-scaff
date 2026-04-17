"""用户相关用例编排（注册、登录等）。

口令哈希统一经本服务调用 ``app.common.utils.password``，勿在 Router 或 ORM Model 中直写 bcrypt。
"""

from app.common.utils.password import hash_password, verify_password


class UserService:
    """用户用例：实现注册/登录时在方法内使用 ``hash_password`` / ``verify_password``。"""

    @staticmethod
    def hash_password_for_storage(plain: str) -> str:
        return hash_password(plain)

    @staticmethod
    def verify_login_password(plain: str, stored_hash: str) -> bool:
        return verify_password(plain, stored_hash)

from app.application.user.service import UserService


def get_user_service() -> UserService:
    """注入 UserService（Session 由 Service 内 SessionProvider 管理）。"""
    return UserService()

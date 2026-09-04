from sqlalchemy import DateTime, String

from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.infrastructure.database.orm.main import MainBase
from database.main.model_registry import load_main_database_metadata


def test_main_database_model_registry_loads_user_model() -> None:
    metadata = load_main_database_metadata()
    users_table = UserModel.__table__

    assert metadata is MainBase.metadata
    assert UserModel.__tablename__ == "users"
    assert users_table is metadata.tables["users"]
    assert users_table.primary_key.name == "pk_users"
    assert users_table.comment == "用户信息"
    assert isinstance(users_table.c.id.type, String)
    assert users_table.c.id.type.length == 36
    assert isinstance(users_table.c.created_at.type, DateTime)
    assert isinstance(users_table.c.updated_at.type, DateTime)
    assert users_table.c.created_at.type.timezone is False
    assert users_table.c.updated_at.type.timezone is False
    assert {column.name: column.comment for column in users_table.columns} == {
        "id": "用户 ID",
        "username": "用户名",
        "email": "邮箱地址",
        "password": "密码哈希",
        "status": "用户状态",
        "created_at": "创建时间",
        "updated_at": "更新时间",
    }

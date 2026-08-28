from typing import ClassVar, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.orm import Mapped, mapped_column

from app.contexts.user.infrastructure.persistence.model import UserRecord
from app.infrastructure.database.orm.main import MAIN_TABLE_PREFIX, MainBase, main_table_name
from database.main.model_registry import load_main_database_metadata


def test_main_database_model_registry_loads_user_model() -> None:
    metadata = load_main_database_metadata()
    users_table = UserRecord.__table__

    assert metadata is MainBase.metadata
    assert users_table is metadata.tables[main_table_name("users")]
    assert users_table.comment == "用户信息"
    assert {column.name: column.comment for column in users_table.columns} == {
        "id": "用户 ID",
        "username": "用户名",
        "email": "邮箱地址",
        "display_name": "显示名称",
        "status": "用户状态",
        "created_at": "创建时间",
        "updated_at": "更新时间",
    }


def test_main_model_uses_configured_table_prefix_and_constraint_names() -> None:
    class ExampleModel(MainBase):
        __table_name__: ClassVar[str] = "orm_prefix_examples"

        id: Mapped[int] = mapped_column(primary_key=True)

    expected_table_name = f"{MAIN_TABLE_PREFIX}orm_prefix_examples"
    table = cast(Table, ExampleModel.__table__)

    assert main_table_name("orm_prefix_examples") == expected_table_name
    assert ExampleModel.__tablename__ == expected_table_name
    assert table.primary_key.name == f"pk_{expected_table_name}"
    assert expected_table_name in MainBase.metadata.tables

    MainBase.metadata.remove(table)


def test_main_model_requires_explicit_core_table_name() -> None:
    with pytest.raises(TypeError, match="__table_name__"):

        class MissingTableNameModel(MainBase):
            id: Mapped[int] = mapped_column(primary_key=True)

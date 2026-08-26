from typing import ClassVar, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MAIN_TABLE_PREFIX, MainBase, main_table_name


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

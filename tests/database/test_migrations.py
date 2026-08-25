import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.runtime.paths import PROJECT_ROOT


def test_main_migration_environment_creates_version_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration.sqlite"
    connections = {
        "main": {
            "driver": "sqlite",
            "database": str(database_path),
            "table_prefix": "",
        }
    }
    monkeypatch.setenv("DB_CONNECTIONS", json.dumps(connections))

    alembic_config = Config(str(PROJECT_ROOT / "database/main/alembic.ini"))

    command.ensure_version(alembic_config)

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }

    assert "alembic_version" in table_names

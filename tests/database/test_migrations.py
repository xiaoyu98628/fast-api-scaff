import json
import shutil
import sqlite3
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config

from app.config.database import DatabaseSettings
from app.runtime.paths import PROJECT_ROOT


def test_main_migration_template_provides_dynamic_table_name_helper(tmp_path: Path) -> None:
    source_directory = PROJECT_ROOT / "database/main/migrations"
    script_directory = tmp_path / "migrations"
    versions_directory = script_directory / "versions"
    versions_directory.mkdir(parents=True)
    shutil.copyfile(source_directory / "script.py.mako", script_directory / "script.py.mako")

    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(script_directory))

    command.revision(alembic_config, message="dynamic table name")

    generated_files = tuple(versions_directory.glob("*.py"))
    assert len(generated_files) == 1

    generated_source = generated_files[0].read_text(encoding="utf-8")
    assert "from app.infrastructure.database.orm.main import main_table_name" in generated_source
    assert "def table_name(name: str) -> str:" in generated_source
    compile(generated_source, str(generated_files[0]), "exec")


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
    model_config = cast(dict[str, object], DatabaseSettings.model_config)
    monkeypatch.setitem(model_config, "env_file", None)
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

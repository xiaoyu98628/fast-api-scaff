from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.config.database import DatabaseSettings
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.failed.sql.model import FailedJobModel
from app.infrastructure.queue.failed.sql.store import SqlFailedJobStore


@pytest.mark.asyncio
async def test_sql_failure_store_survives_new_instance_and_is_idempotent(tmp_path: Path) -> None:
    databases = DatabaseManager(
        DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": str(tmp_path / "failed.sqlite")}})
    )
    engine = await databases.get_engine("main")
    async with engine.begin() as connection:
        await connection.run_sync(FailedJobModel.metadata.create_all)
    first = SqlFailedJobStore(databases)
    record = FailedJobRecord(uuid4(), b"raw", "main", "jobs", datetime.now(), 3, "handler_error", uuid4())
    await first.save(record)
    await first.save(replace(record, payload=b"different"))
    second = SqlFailedJobStore(databases)
    assert await second.find(record.failure_id) == record
    assert await second.list(limit=1) == [record]
    assert await second.list(offset=1) == []
    await second.delete(record.failure_id)
    assert await first.find(record.failure_id) is None
    await databases.aclose()


def test_failed_table_migration_roundtrip(tmp_path: Path) -> None:
    import sqlite3

    from tests.database.test_migrations import run_migration

    path = tmp_path / "migration.sqlite"
    run_migration(path, "upgrade", "head")
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(queue_failed_jobs)")}
    assert columns == {"failure_id", "job_id", "payload", "connection", "queue", "failed_at", "attempts", "reason"}
    run_migration(path, "downgrade", "base")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='queue_failed_jobs'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='user_sessions'").fetchone() is None
    run_migration(path, "upgrade", "head")

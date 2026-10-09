"""验证 SQL 失败存储的并发保存、取消、分页和幂等写入。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
    record = FailedJobRecord(
        uuid4(),
        b"raw",
        "main",
        "jobs",
        datetime.now(),
        3,
        "handler_error",
        uuid4(),
        "builtins.ValueError",
        ({"module": "tests.jobs", "function": "ExampleJob.handle", "line": 27},),
    )
    await first.save(record)
    await first.save(replace(record, payload=b"different"))
    second = SqlFailedJobStore(databases)
    assert await second.find(record.failure_id) == record
    assert await second.list(limit=1) == [record]
    assert await second.list(offset=1) == []
    await second.delete(record.failure_id)
    assert await first.find(record.failure_id) is None
    await databases.aclose()


@pytest.mark.asyncio
async def test_sql_failure_store_serializes_concurrent_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    databases = DatabaseManager(
        DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": str(tmp_path / "concurrent.sqlite")}})
    )
    engine = await databases.get_engine("main")
    async with engine.begin() as connection:
        await connection.run_sync(FailedJobModel.metadata.create_all)
    original_session = databases.session
    active = peak = 0

    @asynccontextmanager
    async def tracked_session(name: str | None = None) -> AsyncIterator[AsyncSession]:
        nonlocal active, peak
        async with original_session(name) as session:
            active += 1
            peak = max(peak, active)
            try:
                # 主动让出执行权，确保无串行保护时可以观测到多个保存事务同时进入。
                await asyncio.sleep(0)
                yield session
            finally:
                active -= 1

    monkeypatch.setattr(databases, "session", tracked_session)
    store = SqlFailedJobStore(databases)
    records = [_failure_record(payload=f"failure-{index}".encode()) for index in range(8)]
    tasks = [asyncio.create_task(store.save(record)) for record in (*records, replace(records[0], payload=b"later"))]
    try:
        async with asyncio.timeout(10):
            await asyncio.gather(*tasks)
            saved = await store.list(limit=20)
        assert peak == 1
        assert {record.failure_id for record in saved} == {record.failure_id for record in records}
        assert next(record for record in saved if record.failure_id == records[0].failure_id) == records[0]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await databases.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_sql_failure_store_releases_write_lock_after_interruption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool) -> None:
    databases = DatabaseManager(
        DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": str(tmp_path / "interrupted.sqlite")}})
    )
    engine = await databases.get_engine("main")
    async with engine.begin() as connection:
        await connection.run_sync(FailedJobModel.metadata.create_all)
    original_session = databases.session
    started = asyncio.Event()
    release = asyncio.Event()
    first_call = True

    @asynccontextmanager
    async def interrupted_session(name: str | None = None) -> AsyncIterator[AsyncSession]:
        nonlocal first_call
        async with original_session(name) as session:
            if first_call:
                first_call = False
                started.set()
                await release.wait()
                raise RuntimeError("保存中断")
            yield session

    monkeypatch.setattr(databases, "session", interrupted_session)
    store = SqlFailedJobStore(databases)
    first, second = _failure_record(), _failure_record()
    task = asyncio.create_task(store.save(first))
    try:
        async with asyncio.timeout(10):
            await started.wait()
            if cancel:
                task.cancel()
            else:
                release.set()
            with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
                await task
            await store.save(second)
            assert await store.find(first.failure_id) is None
            assert await store.find(second.failure_id) == second
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await databases.aclose()


def _failure_record(*, payload: bytes = b"raw") -> FailedJobRecord:
    """创建供并发测试独立保存的失败记录。"""

    return FailedJobRecord(
        failure_id=uuid4(),
        payload=payload,
        connection="main",
        queue="jobs",
        failed_at=datetime.now(),
        attempts=1,
        reason="handler_error",
    )


def test_failed_table_migration_roundtrip(tmp_path: Path) -> None:
    import sqlite3

    from tests.database.test_migrations import run_migration

    path = tmp_path / "migration.sqlite"
    run_migration(path, "upgrade", "head")
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(queue_failed_jobs)")}
    assert columns == {
        "failure_id",
        "job_id",
        "payload",
        "connection",
        "queue",
        "failed_at",
        "attempts",
        "reason",
        "error_type",
        "stacktrace",
    }
    run_migration(path, "downgrade", "base")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='queue_failed_jobs'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='users'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='user_sessions'").fetchone() is None
    run_migration(path, "upgrade", "head")

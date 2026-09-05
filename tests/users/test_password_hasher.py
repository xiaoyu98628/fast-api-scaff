import asyncio
import threading

import pytest
from anyio import CancelScope
from pwdlib import PasswordHash as PwdlibPasswordHash

from app.contexts.user.domain.values import Password
from app.contexts.user.infrastructure.security.password_hasher import PwdlibPasswordHasher


@pytest.mark.asyncio
async def test_pwdlib_password_hasher_generates_verifiable_non_plaintext_hash() -> None:
    plaintext = "correct-horse-battery-staple"

    password_hash = await PwdlibPasswordHasher().hash(Password(plaintext))

    assert password_hash.value != plaintext
    assert password_hash.value.startswith("$argon2")
    assert PwdlibPasswordHash.recommended().verify(plaintext, password_hash.value) is True


@pytest.mark.asyncio
async def test_hash_runs_off_event_loop_and_limits_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    hasher = PwdlibPasswordHasher(max_concurrency=1)
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    calls: list[str] = []

    def blocking_hash(password: str) -> str:
        assert threading.get_ident() != loop_thread
        calls.append(password)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5), "Hash worker was not released"
        return "test-hash"

    loop_thread = threading.get_ident()
    monkeypatch.setattr(hasher._hasher, "hash", blocking_hash)
    tasks = [asyncio.create_task(hasher.hash(Password(value))) for value in ("password-one", "password-two")]
    try:
        async with asyncio.timeout(5):
            await started.wait()
            while hasher._limiter.statistics().tasks_waiting != 1:
                await asyncio.sleep(0)
            assert calls == ["password-one"]
            assert not any(task.done() for task in tasks)
    finally:
        release.set()
        results = await asyncio.gather(*tasks)
    assert [result.value for result in results] == ["test-hash", "test-hash"]
    assert calls == ["password-one", "password-two"]


@pytest.mark.parametrize("cancel_mode", ["asyncio", "anyio"])
@pytest.mark.asyncio
async def test_cancelled_hash_holds_capacity_until_worker_finishes(monkeypatch: pytest.MonkeyPatch, cancel_mode: str) -> None:
    hasher = PwdlibPasswordHasher(max_concurrency=1)
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    calls: list[str] = []
    scopes: list[CancelScope] = []

    def blocking_hash(password: str) -> str:
        calls.append(password)
        if password == "password-one":
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5), "Hash worker was not released"
        return "test-hash"

    async def first_hash() -> None:
        with CancelScope() as scope:
            scopes.append(scope)
            await hasher.hash(Password("password-one"))

    monkeypatch.setattr(hasher._hasher, "hash", blocking_hash)
    first = asyncio.create_task(first_hash())
    second: asyncio.Task | None = None
    try:
        async with asyncio.timeout(5):
            await started.wait()
            if cancel_mode == "asyncio":
                first.cancel()
                await asyncio.sleep(0)
                first.cancel()
            else:
                scopes[0].cancel()
            second = asyncio.create_task(hasher.hash(Password("password-two")))
            while hasher._limiter.statistics().tasks_waiting != 1:
                await asyncio.sleep(0)
            assert not first.done()
            assert calls == ["password-one"]
    finally:
        release.set()
        results = await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)
    if cancel_mode == "asyncio":
        assert isinstance(results[0], asyncio.CancelledError)
    else:
        assert scopes[0].cancelled_caught
    assert second is not None
    assert second.result().value == "test-hash"
    assert hasher._limiter.borrowed_tokens == 0


@pytest.mark.asyncio
async def test_hash_failure_releases_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    hasher = PwdlibPasswordHasher(max_concurrency=1)
    original = RuntimeError("hash failed")

    def failing_hash(_password: str) -> str:
        raise original

    monkeypatch.setattr(hasher._hasher, "hash", failing_hash)
    with pytest.raises(RuntimeError) as captured:
        await hasher.hash(Password("password123"))
    assert captured.value is original
    assert hasher._limiter.borrowed_tokens == 0

from app.infrastructure.http.drivers.httpx2.pool import HttpPoolRuntime


def test_pool_runtime_reports_each_pressure_episode_once() -> None:
    runtime = HttpPoolRuntime(name="standard", limit=4, warning_ratio=0.5)

    assert runtime.acquire() is False
    assert runtime.acquire() is True
    assert runtime.acquire() is False

    runtime.release()
    runtime.release()

    assert runtime.acquire() is True
    assert runtime.log_details()["limit"] == 4
    assert runtime.log_details()["usage"] == 0.5

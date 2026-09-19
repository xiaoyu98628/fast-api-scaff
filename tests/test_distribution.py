"""验证构建产物包含并能加载运行时所需的非 Python 资源。"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from app.runtime.paths import PROJECT_ROOT

_LUA_RESOURCES = {
    "app/contexts/user/infrastructure/security/scripts/delete_below.lua",
    "app/contexts/user/infrastructure/security/scripts/increment_with_ttl.lua",
    "app/infrastructure/rate_limit/scripts/acquire_window.lua",
}


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"命令执行失败：{' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return result


def test_wheel_contains_and_loads_redis_lua_resources(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "构建产物测试需要 uv"

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(tmp_path / "uv-cache")

    dist_directory = tmp_path / "dist"
    _run(
        [
            uv,
            "build",
            "--wheel",
            "--no-sources",
            "--out-dir",
            str(dist_directory),
            "--no-create-gitignore",
        ],
        cwd=PROJECT_ROOT,
        env=env,
    )

    wheels = list(dist_directory.glob("*.whl"))
    assert len(wheels) == 1

    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        packaged_files = set(archive.namelist())

    assert _LUA_RESOURCES <= packaged_files

    installed_directory = tmp_path / "installed"
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(installed_directory),
            "--no-deps",
            str(wheel),
        ],
        cwd=tmp_path,
        env=env,
    )

    load_script = """
from pathlib import Path
import sys

import app.contexts.user.infrastructure.security.redis_login_attempts as login
import app.infrastructure.rate_limit.redis as rate_limit

installed_root = Path(sys.argv[1]).resolve()
assert Path(login.__file__).resolve().is_relative_to(installed_root)
assert Path(rate_limit.__file__).resolve().is_relative_to(installed_root)
assert "redis.call" in login._INCREMENT_SCRIPT
assert "redis.call" in login._CLEAR_SCRIPT
assert "redis.call" in rate_limit._WINDOW_SCRIPT
"""
    load_env = env | {"PYTHONPATH": str(installed_directory)}
    _run(
        [
            sys.executable,
            "-c",
            load_script,
            str(installed_directory),
        ],
        cwd=tmp_path,
        env=load_env,
    )

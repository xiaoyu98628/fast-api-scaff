"""
配置包：子模块按 ``APP_*`` / ``DB_*`` / ``REDIS_*`` 等前缀从环境变量与 ``.env`` 加载。

``BASE_DIR`` 为项目根目录（含 ``app/``、``config/`` 的上一级），供各 Settings 定位 ``.env``。
``SERVICE_CODE`` 等无前缀变量由 ``ServiceSettings`` 读取（见 ``config.service``）。
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "storage"
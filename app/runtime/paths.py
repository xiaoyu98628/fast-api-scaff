"""集中定义不依赖当前工作目录的项目运行时路径。"""

from pathlib import Path

# 从当前模块位置推导根目录，保证从任意目录启动命令都能定位资源。
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_FILE = PROJECT_ROOT / ".env"
STORAGE_DIR = PROJECT_ROOT / "storage"

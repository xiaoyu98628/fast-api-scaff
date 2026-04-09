"""应用根包。分层目录与职责见各子包顶部的模块说明。"""

from pathlib import Path

# 本包目录（.../app），用于静态资源路径等
APP_DIR = Path(__file__).resolve().parent
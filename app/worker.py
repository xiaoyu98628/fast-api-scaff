"""创建并运行独立队列 Worker 的命令入口。"""

from app.bootstrap.worker.application import WorkerHost
from app.bootstrap.worker.logging import configure_worker_logging
from app.config.settings import load_settings
from app.interfaces.worker.cli import create_worker, run_worker


def _run() -> None:
    """在统一错误边界内加载配置并执行 Worker 命令。"""

    settings = load_settings()
    configure_worker_logging(settings)
    worker = WorkerHost(settings)
    create_worker(worker.run)()


def main() -> None:
    """解析 Worker CLI 参数并启动消费循环。"""

    run_worker(_run)


if __name__ == "__main__":
    main()

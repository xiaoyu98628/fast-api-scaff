"""创建并运行独立队列 Worker 的命令入口。"""

from app.bootstrap.worker.application import WorkerHost
from app.bootstrap.worker.logging import configure_worker_logging
from app.config.settings import load_settings
from app.interfaces.worker.cli import create_worker, run_worker

# CLI 回调复用同一个宿主对象，但每次执行仍由 WorkerHost 创建独立运行时。
settings = load_settings()
configure_worker_logging(settings)

_worker = WorkerHost(settings)
app = create_worker(_worker.run)


def main() -> None:
    """解析 Worker CLI 参数并启动消费循环。"""

    run_worker(app)


if __name__ == "__main__":
    main()

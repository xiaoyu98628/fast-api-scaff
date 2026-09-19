"""创建并运行独立 Scheduler 进程。"""

from app.bootstrap.scheduler.application import SchedulerHost
from app.bootstrap.scheduler.logging import configure_scheduler_logging
from app.config.settings import load_settings
from app.interfaces.scheduler.cli import run_scheduler


def _run() -> None:
    """在统一错误边界内加载配置并执行 Scheduler。"""

    settings = load_settings()
    configure_scheduler_logging(settings)
    SchedulerHost(settings).run()


def main() -> None:
    """启动常驻 Scheduler 宿主。"""

    run_scheduler(_run)


if __name__ == "__main__":
    main()

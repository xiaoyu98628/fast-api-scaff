from app.bootstrap.worker.application import WorkerHost
from app.bootstrap.worker.logging import configure_worker_logging
from app.config.settings import load_settings
from app.interfaces.worker.cli import create_worker, run_worker

settings = load_settings()
configure_worker_logging(settings)

_worker = WorkerHost(settings)
app = create_worker(_worker.run)


def main() -> None:
    run_worker(app)


if __name__ == "__main__":
    main()

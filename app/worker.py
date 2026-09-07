from app.bootstrap.worker.application import WorkerHost
from app.interfaces.worker.cli import create_worker, run_worker

_worker = WorkerHost()
app = create_worker(_worker.run)


def main() -> None:
    run_worker(app)


if __name__ == "__main__":
    main()

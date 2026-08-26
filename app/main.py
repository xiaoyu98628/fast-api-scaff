from app.bootstrap.app import create_app
from app.config.settings import load_settings
from app.infrastructure.logging.configure import configure_logging

settings = load_settings()
configure_logging(settings)

app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="app.main:app",
        reload=settings.app.debug,
        access_log=False,
        log_config=None,
    )

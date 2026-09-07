from app.bootstrap.http.application import create_app
from app.bootstrap.http.logging import configure_http_logging
from app.config.settings import load_settings

settings = load_settings()
configure_http_logging(settings)

app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="app.main:app",
        reload=settings.app.debug,
        access_log=False,
        log_config=None,
    )

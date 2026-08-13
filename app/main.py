from app.bootstrap.app import create_app
from app.config.settings import load_settings

app = create_app()


if __name__ == "__main__":
    import uvicorn

    app_settings = load_settings().app

    uvicorn.run(
        app="app.main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=app_settings.debug,
    )

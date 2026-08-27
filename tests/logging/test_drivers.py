from app.infrastructure.logging.drivers.registry import DEFAULT_LOGGING_DRIVERS
from app.infrastructure.logging.drivers.stream import build_stream_handler


def test_stream_driver_builds_stdout_handler_definition() -> None:
    handler = build_stream_handler(
        {
            "driver": "stream",
            "stream": "stdout",
        }
    )

    assert handler == {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
    }


def test_default_drivers_contains_stream_builder() -> None:
    assert DEFAULT_LOGGING_DRIVERS == {"stream": build_stream_handler}

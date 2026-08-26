import json
import logging

from starlette_context import request_cycle_context
from starlette_context.header_keys import HeaderKeys

from app.infrastructure.logging.formatter import JsonLogFormatter
from app.interfaces.http.logging import HttpLogEvent


def test_json_formatter_renders_structured_event_and_request_id() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test")
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Request completed",
        args=(),
        exc_info=None,
    )
    record.event = HttpLogEvent.REQUEST_COMPLETED
    record.details = {"status_code": 200}

    with request_cycle_context({HeaderKeys.request_id: "request-123"}):
        payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["service"] == "test-service"
    assert payload["environment"] == "test"
    assert payload["message"] == "Request completed"
    assert payload["request_id"] == "request-123"
    assert payload["event"] == "http.request.completed"
    assert payload["details"] == {"status_code": 200}
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_keeps_details_nested() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test")
    record = logging.LogRecord(
        name="app.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=10,
        msg="Message",
        args=(),
        exc_info=None,
    )
    record.details = {"level": "business-value", "message": "detail-message"}

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "WARNING"
    assert payload["message"] == "Message"
    assert payload["details"] == {
        "level": "business-value",
        "message": "detail-message",
    }

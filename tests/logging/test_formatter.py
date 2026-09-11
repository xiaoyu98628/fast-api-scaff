"""验证结构化日志格式、请求上下文和安全异常诊断。"""

import json
import logging
from datetime import datetime

from starlette_context import request_cycle_context
from starlette_context.header_keys import HeaderKeys

from app.infrastructure.logging.context import JobLogContext, RuntimeContextFilter, bind_job_log_context
from app.infrastructure.logging.formatter import JsonLogFormatter, TextLogFormatter
from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.interfaces.http.logging import HttpLogEvent


def test_json_formatter_renders_structured_event_and_request_id() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test", service_version="1.2.3")
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
    record.created = 1_700_000_000.123

    with request_cycle_context({HeaderKeys.request_id: "request-123"}):
        RuntimeContextFilter().filter(record)

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["service"] == "test-service"
    assert payload["environment"] == "test"
    assert payload["service_version"] == "1.2.3"
    assert payload["message"] == "Request completed"
    assert payload["request_id"] == "request-123"
    assert payload["event"] == "http.request.completed"
    assert payload["details"] == {"status_code": 200}
    assert payload["timestamp"] == _local_timestamp(record.created)


def test_json_formatter_keeps_details_nested() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test", service_version="1.2.3")
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


def test_json_formatter_renders_scoped_job_context_and_clears_it() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test", service_version="1.2.3")
    record = logging.LogRecord("app.test", logging.INFO, __file__, 10, "Job log", (), None)
    job_context = JobLogContext(
        job_id="job-123",
        job_type="app.jobs:ExampleJob",
        job_version=2,
        queue_connection="redis",
        queue_name="reports",
        correlation_id="request-123",
        replay_of="failure-123",
    )

    with bind_job_log_context(job_context):
        RuntimeContextFilter().filter(record)

    payload = formatter.build_payload(record)
    assert payload["job_id"] == "job-123"
    assert payload["job_type"] == "app.jobs:ExampleJob"
    assert payload["job_version"] == 2
    assert payload["queue_connection"] == "redis"
    assert payload["queue_name"] == "reports"
    assert payload["correlation_id"] == "request-123"
    assert payload["replay_of"] == "failure-123"

    unrelated = logging.LogRecord("app.test", logging.INFO, __file__, 10, "Other log", (), None)
    RuntimeContextFilter().filter(unrelated)
    assert "job_id" not in formatter.build_payload(unrelated)


def test_text_formatter_renders_structured_fields_on_one_line() -> None:
    formatter = TextLogFormatter(service="test-service", environment="test", service_version="1.2.3")
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Request completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-123"
    record.event = HttpLogEvent.REQUEST_COMPLETED
    record.details = {"status_code": 200}
    record.created = 1_700_000_000.123

    rendered = formatter.format(record)

    assert "\n" not in rendered
    assert f'timestamp="{_local_timestamp(record.created)}"' in rendered
    assert 'level="INFO"' in rendered
    assert 'logger="app.test"' in rendered
    assert 'service="test-service"' in rendered
    assert 'environment="test"' in rendered
    assert 'service_version="1.2.3"' in rendered
    assert 'message="Request completed"' in rendered
    assert 'request_id="request-123"' in rendered
    assert 'event="http.request.completed"' in rendered
    assert 'details={"status_code":200}' in rendered


def test_text_formatter_keeps_exception_on_one_line() -> None:
    formatter = TextLogFormatter(service="test-service", environment="test", service_version="1.2.3")

    try:
        raise ValueError("invalid\nvalue")
    except ValueError as error:
        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg="Operation failed",
            args=(),
            exc_info=(type(error), error, error.__traceback__),
        )

    rendered = formatter.format(record)

    assert "\n" not in rendered
    assert 'message="Operation failed"' in rendered
    assert 'exception={"type":"ValueError","message":"invalid\\nvalue","stacktrace":"Traceback' in rendered


def test_json_formatter_uses_runtime_local_timezone() -> None:
    formatter = JsonLogFormatter(service="test-service", environment="test", service_version="1.2.3")
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Message",
        args=(),
        exc_info=None,
    )
    record.created = 1_700_000_000.123

    payload = json.loads(formatter.format(record))

    assert payload["timestamp"] == _local_timestamp(record.created)


def test_log_extra_builds_standard_event_and_details() -> None:
    extra = log_extra(HttpLogEvent.REQUEST_COMPLETED, status_code=200)

    assert extra == {
        "event": HttpLogEvent.REQUEST_COMPLETED,
        "details": {"status_code": 200},
    }


def test_safe_exception_details_excludes_message_and_runtime_values() -> None:
    """安全诊断只保留异常类型和代码位置。"""

    secret = "sensitive runtime value"
    try:
        raise ValueError(secret)
    except ValueError as error:
        error_type, stacktrace = safe_exception_details(error)

    assert error_type == "builtins.ValueError"
    assert stacktrace[-1]["module"] == __name__
    assert stacktrace[-1]["function"] == "test_safe_exception_details_excludes_message_and_runtime_values"
    assert isinstance(stacktrace[-1]["line"], int)
    assert secret not in repr((error_type, stacktrace))


def _local_timestamp(created: float) -> str:
    return datetime.fromtimestamp(created).astimezone().isoformat(timespec="milliseconds")

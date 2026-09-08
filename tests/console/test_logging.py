"""验证 Console 日志统一写入标准错误流。"""

from app.bootstrap.console.logging import build_console_stream_handler


def test_console_stream_logging_uses_stderr() -> None:
    stdout_handler = build_console_stream_handler({"driver": "stream", "stream": "stdout"})
    stderr_handler = build_console_stream_handler({"driver": "stream", "stream": "stderr"})

    assert stdout_handler["stream"] == "ext://sys.stderr"
    assert stderr_handler["stream"] == "ext://sys.stderr"

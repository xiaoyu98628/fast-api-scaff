import logging

from app.infrastructure.context.request_scope import get_trace_id


class TraceIdFilter(logging.Filter):
    """为每条记录补上 ``trace_id``（供 format 使用）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        return True



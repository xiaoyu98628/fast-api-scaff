from enum import StrEnum


class HttpLogEvent(StrEnum):
    REQUEST_COMPLETED = "http.request.completed"

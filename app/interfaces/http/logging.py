from enum import StrEnum


class HttpLogEvent(StrEnum):
    INVALID_REQUEST_ID = "http.request.invalid_request_id"
    REQUEST_COMPLETED = "http.request.completed"
    UNHANDLED_EXCEPTION = "http.request.unhandled_exception"

from enum import StrEnum


class ApplicationLogEvent(StrEnum):
    STARTING = "application.starting"
    STARTED = "application.started"
    START_FAILED = "application.start_failed"
    STOPPING = "application.stopping"
    STOPPED = "application.stopped"
    STOP_FAILED = "application.stop_failed"

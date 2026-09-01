import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import pytest

from app.contexts.user.domain.values import UserStatus
from app.interfaces.console.presentation import ConsolePresenter


@dataclass(frozen=True, slots=True)
class ExampleResult:
    id: UUID
    status: UserStatus
    created_at: datetime


def test_console_presenter_separates_result_and_error_streams(capsys: pytest.CaptureFixture[str]) -> None:
    presenter = ConsolePresenter()
    presenter.result(
        ExampleResult(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            status=UserStatus.ACTIVE,
            created_at=datetime(2026, 8, 31, 12, 30),
        )
    )
    result_output = capsys.readouterr()

    presenter.error("operation failed")
    error_output = capsys.readouterr()

    assert json.loads(result_output.out) == {
        "id": "00000000-0000-0000-0000-000000000001",
        "status": "active",
        "created_at": "2026-08-31T12:30:00",
    }
    assert result_output.err == ""
    assert error_output.out == ""
    assert error_output.err.strip() == "Error: operation failed"

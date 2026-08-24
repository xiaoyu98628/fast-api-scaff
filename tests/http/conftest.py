import pytest

import app.interfaces.http.shared.response.codes.builder as response_code_builder_module


@pytest.fixture(autouse=True)
def reset_response_code_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(response_code_builder_module, "_response_code_builder", None)

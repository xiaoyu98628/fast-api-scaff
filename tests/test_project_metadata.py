import tomllib

from app.config.app import AppSettings
from app.runtime.paths import PROJECT_ROOT


def test_project_metadata_is_complete_and_matches_runtime_default() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["description"] != "Add your description here"
    assert AppSettings(_env_file=None).version == project["version"]


def test_sample_environment_version_matches_project_metadata() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    sample_lines = (PROJECT_ROOT / "sample.env").read_text(encoding="utf-8").splitlines()
    sample_version = next(line.removeprefix("APP_VERSION=") for line in sample_lines if line.startswith("APP_VERSION="))

    assert sample_version == project["version"]

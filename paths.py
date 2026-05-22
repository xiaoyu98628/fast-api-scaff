
from pathlib import Path


BASE_DIR: Path = Path(__file__).resolve().parent

ENV_FILE: Path = BASE_DIR.joinpath(".env")

print(ENV_FILE)
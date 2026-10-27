import functools
import os
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def get_version() -> str:
    # Docker images get a VERSION file written at build time (the image has
    # no .git); git installs report their checked-out tag via `git describe`.
    version_file = APP_DIR / "VERSION"

    if version_file.is_file():
        value = version_file.read_text().strip()

        if value:
            return value

    if (APP_DIR / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                cwd=APP_DIR, capture_output=True, text=True, timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass

    return "dev"


def is_docker() -> bool:
    return bool(os.getenv("TELEFIN_DOCKER"))

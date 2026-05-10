import os
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def load_allowed_users() -> list[int]:
    """
    Load allowed Telegram user IDs from environment variable.

    Example:
        ALLOWED_USERS=12345,67890
    """
    raw_users = os.getenv("ALLOWED_USERS", "")

    if not raw_users:
        logger.warning("No ALLOWED_USERS configured")
        return []

    users = []

    for user_id in raw_users.split(","):
        user_id = user_id.strip()

        if not user_id:
            continue

        try:
            users.append(int(user_id))
        except ValueError:
            logger.warning(f"Invalid Telegram user ID: {user_id}")

    logger.info(f"Loaded {len(users)} allowed users")

    return users


def is_allowed_user(user_id: int, allowed_users: list[int]) -> bool:
    """
    Check if Telegram user is authorized.
    """
    return user_id in allowed_users


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe filesystem usage.
    """
    keepchars = (" ", ".", "_", "-", "[", "]", "(", ")")

    cleaned = "".join(
        c for c in filename
        if c.isalnum() or c in keepchars
    )

    cleaned = cleaned.strip()

    if not cleaned:
        cleaned = "unknown_file"

    return cleaned


def ensure_directory(path: str) -> Path:
    """
    Create directory if it doesn't exist.
    """
    directory = Path(path)

    directory.mkdir(parents=True, exist_ok=True)

    return directory


def format_size(size_bytes: int) -> str:
    """
    Convert bytes to human-readable format.
    """
    if size_bytes == 0:
        return "0B"

    size_names = ("B", "KB", "MB", "GB", "TB")

    i = 0
    size = float(size_bytes)

    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1

    return f"{size:.2f} {size_names[i]}"


def setup_logging(level: str = "INFO") -> None:
    """
    Configure application logging.
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )


def is_tv_show(filename: str) -> bool:
    """
    Detect whether filename looks like a TV episode.

    Matches:
        Show.Name.S01E01.mkv
        Show.Name.1x01.mkv
    """
    patterns = [
        r"s\d{1,2}e\d{1,2}",
        r"\d{1,2}x\d{1,2}",
    ]

    filename = filename.lower()

    for pattern in patterns:
        if re.search(pattern, filename):
            return True

    return False
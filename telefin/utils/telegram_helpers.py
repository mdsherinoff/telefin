import os
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def load_allowed_users() -> list[int]:
    # Load allowed Telegram user IDs from environment variable.
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
    # Check if Telegram user is authorized.
    return user_id in allowed_users


def sanitize_filename(filename: str) -> str:
    # Sanitize filename for safe filesystem usage.
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
    # Create directory if it doesn't exist.
    directory = Path(path)

    directory.mkdir(parents=True, exist_ok=True)

    return directory


def cleanup_orphaned_partials(dirs: list[str]) -> int:
    # Remove .part files left behind by a crash/restart mid-download. Safe
    # to do unconditionally at startup: any download still in flight was
    # just reset to failed (see Database.reset_interrupted), so nothing
    # will resume from these files -- a retry re-downloads from scratch.
    removed = 0

    for directory in dirs:
        path = Path(directory)

        if not path.is_dir():
            continue

        for partial in path.glob("*.part"):
            try:
                partial.unlink()
                removed += 1
            except OSError as e:
                logger.warning("Could not remove orphaned partial %s: %s", partial, e)

    return removed


def format_size(size_bytes: int) -> str:
    # Convert bytes to human-readable format.
    if size_bytes == 0:
        return "0B"

    size_names = ("B", "KB", "MB", "GB", "TB")

    i = 0
    size = float(size_bytes)

    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1

    return f"{size:.2f} {size_names[i]}"


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)

    if not raw:
        return default

    try:
        return int(raw)
    except ValueError:
        return default


def setup_logging(level: str | None = None) -> None:
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    # Bare (non-Docker) deployments often redirect stdout to a plain file,
    # which grows forever. LOG_FILE opts into rotation on top of whatever's
    # already capturing stdout (journald, Docker's log driver, etc.).
    log_file = os.getenv("LOG_FILE")
    if log_file:
        from logging.handlers import RotatingFileHandler

        handlers.append(
            RotatingFileHandler(
                log_file,
                maxBytes=_get_int_env("LOG_MAX_BYTES", 10 * 1024 * 1024),
                backupCount=_get_int_env("LOG_BACKUP_COUNT", 5),
            )
        )

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


def is_tv_show(filename: str) -> bool:
    # Detect whether filename looks like a TV episode.
    # Matches: Show.Name.S01E01.mkv, Show.Name.1x01.mkv
    patterns = [
        r"s\d{1,2}e\d{1,2}",
        r"\d{1,2}x\d{1,2}",
    ]

    filename = filename.lower()

    for pattern in patterns:
        if re.search(pattern, filename):
            return True

    return False

def detect_media_type(filename: str) -> str:
    return "tv" if is_tv_show(filename) else "movie"

def safe_destination(download_dir: str, filename: str) -> tuple[str, str]:
    base = os.path.basename(filename)
    safe_name = sanitize_filename(base)
    dest_path = os.path.join(download_dir, safe_name)

    if not os.path.exists(dest_path):
        return safe_name, dest_path

    # Another (differently-sized) file already sits at this path -- true
    # duplicates are caught earlier via find_completed_duplicate, so this
    # collision is a distinct file that happens to sanitize to the same
    # name. Suffix it rather than risk clobbering the existing one.
    stem, ext = os.path.splitext(safe_name)
    counter = 1

    while os.path.exists(dest_path):
        candidate = f"{stem} ({counter}){ext}"
        dest_path = os.path.join(download_dir, candidate)
        counter += 1

    return os.path.basename(dest_path), dest_path

# Render a text progress bar
def make_progress_bar(fraction: float, width: int = 16) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))

    return "[" + "█" * filled + "░" * (width - filled) + "]"

# show transfer speed
def format_speed(bytes_per_second: float) -> str:
    return f"{format_size(int(bytes_per_second))}/s"
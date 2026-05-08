import os
import logging
from pathlib import Path
from telegram import Update
from telegram.constants import ChatAction
import re

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


async def reject_unauthorized_user(update: Update) -> None:
    """
    Send rejection message to unauthorized users.
    """
    try:
        await update.message.reply_text(
            "You are not authorized to use this bot."
        )
    except Exception as e:
        logger.error(f"Failed to send unauthorized message: {e}")


async def send_typing(update: Update) -> None:
    """
    Display Telegram 'typing...' indicator.
    """
    try:
        await update.message.chat.send_action(
            action=ChatAction.TYPING
        )
    except Exception as e:
        logger.error(f"Failed to send typing action: {e}")


async def send_uploading(update: Update) -> None:
    """
    Display Telegram 'uploading...' indicator.
    """
    try:
        await update.message.chat.send_action(
            action=ChatAction.UPLOAD_DOCUMENT
        )
    except Exception as e:
        logger.error(f"Failed to send upload action: {e}")


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


def get_download_path(download_dir: str, filename: str) -> Path:
    """
    Build safe download path.
    """
    safe_name = sanitize_filename(filename)

    return Path(download_dir) / safe_name


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


def detect_media_type(filename: str) -> str:
    """
    Detect media type based on file extension.
    """

    extension = Path(filename).suffix.lower()

    movie_extensions = {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm"
    }

    subtitle_extensions = {
        ".srt",
        ".ass",
        ".vtt",
        ".sub"
    }

    audio_extensions = {
        ".mp3",
        ".flac",
        ".aac",
        ".wav",
        ".ogg",
        ".m4a"
    }

    if extension in movie_extensions:
        return "video"

    if extension in subtitle_extensions:
        return "subtitle"

    if extension in audio_extensions:
        return "audio"

    return "unknown"


async def send_success_message(
    update: Update,
    filename: str,
    path: str
) -> None:
    """
    Send successful download confirmation.
    """
    try:
        await update.message.reply_text(
            (
                f"Download complete\n\n"
                f"File: {filename}\n"
                f"Saved to: {path}\n\n"
                f"Sonarr/Radarr import can now begin."
            )
        )

    except Exception as e:
        logger.error(f"Failed to send success message: {e}")


async def send_error_message(
    update: Update,
    error: str
) -> None:
    """
    Send formatted error message.
    """
    try:
        await update.message.reply_text(
            (
                f"Error\n\n"
                f"{error}"
            )
        )

    except Exception as e:
        logger.error(f"Failed to send error message: {e}")


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
    """

    patterns = [
        r"s\d{1,2}e\d{1,2}",   # S01E01
        r"\d{1,2}x\d{1,2}",    # 1x01
    ]

    filename = filename.lower()

    for pattern in patterns:
        if re.search(pattern, filename):
            return True

    return False
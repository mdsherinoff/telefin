import os
import re
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables from .env once, at import time.
load_dotenv()

# Default set of video extensions we are willing to download.
DEFAULT_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov",
    ".wmv", ".flv", ".webm", ".m4v",
}

def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in ("1", "true", "yes", "on")

def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    try:
        return int(raw)
    except ValueError:
        return default

def _parse_extensions(raw: str) -> set[str]:
    extensions = set()

    for item in raw.split(","):
        item = item.strip().lower()

        if not item:
            continue

        if not item.startswith("."):
            item = "." + item

        extensions.add(item)

    return extensions or set(DEFAULT_EXTENSIONS)

def _parse_chats(raw: str) -> list:
    # WATCH_CHAT may name one or more sources, comma separated:
    #   "me"                    -> your own Saved Messages
    #   "-1001234567890"        -> a (super)group / channel, by numeric ID
    #   "@somegroup"            -> a public username
    #   "me,-1001234567890"     -> watch both at once
    # Numeric entries must become ints, otherwise Telethon treats them as
    # usernames and fails to resolve the group.
    chats: list = []

    for item in raw.split(","):
        item = item.strip()

        if not item:
            continue

        if re.fullmatch(r"-?\d+", item):
            chats.append(int(item))
        else:
            chats.append(item)

    return chats or ["me"]

@dataclass
class Config:
    # Telegram
    api_id: int
    api_hash: str
    session_name: str
    watch_chats: list
    allowed_users: list[int]

    # Storage
    download_dir: str
    download_dir_movies: str | None
    download_dir_tv: str | None
    db_path: str

    # Downloads
    allowed_extensions: set[str]
    max_concurrent_downloads: int
    progress_interval: int
    max_download_retries: int
    retry_backoff_seconds: int

    # Sonarr / Radarr
    sonarr_url: str | None
    sonarr_api_key: str | None
    radarr_url: str | None
    radarr_api_key: str | None

    # Web dashboard
    web_enabled: bool
    web_host: str
    web_port: int
    web_username: str | None
    web_password: str | None

    @classmethod
    def from_env(cls) -> "Config":
        raw_extensions = os.getenv("ALLOWED_EXTENSIONS", "")

        return cls(
            api_id=_get_int("TELEGRAM_API_ID", 0),
            api_hash=os.getenv("TELEGRAM_API_HASH", ""),
            session_name=os.getenv("SESSION_NAME", "userbot_session"),
            watch_chats=_parse_chats(os.getenv("WATCH_CHAT", "me")),
            allowed_users=_parse_users(os.getenv("ALLOWED_USERS", "")),
            download_dir=os.getenv("DOWNLOAD_DIR", "/srv/media/incoming"),
            download_dir_movies=os.getenv("DOWNLOAD_DIR_MOVIES") or None,
            download_dir_tv=os.getenv("DOWNLOAD_DIR_TV") or None,
            db_path=os.getenv("DB_PATH", "telefin.db"),
            allowed_extensions=(
                _parse_extensions(raw_extensions)
                if raw_extensions
                else set(DEFAULT_EXTENSIONS)
            ),
            max_concurrent_downloads=_get_int("MAX_CONCURRENT_DOWNLOADS", 1),
            progress_interval=_get_int("PROGRESS_INTERVAL", 5),
            max_download_retries=_get_int("MAX_DOWNLOAD_RETRIES", 3),
            retry_backoff_seconds=_get_int("RETRY_BACKOFF_SECONDS", 10),
            sonarr_url=os.getenv("SONARR_URL"),
            sonarr_api_key=os.getenv("SONARR_API_KEY"),
            radarr_url=os.getenv("RADARR_URL"),
            radarr_api_key=os.getenv("RADARR_API_KEY"),
            web_enabled=_get_bool("WEB_ENABLED", True),
            web_host=os.getenv("WEB_HOST", "0.0.0.0"),
            web_port=_get_int("WEB_PORT", 8420),
            web_username=os.getenv("WEB_USERNAME") or None,
            web_password=os.getenv("WEB_PASSWORD") or None,
        )

    def download_dir_for(self, media_type: str) -> str:
        # media_type is "tv" or "movie" (see detect_media_type). Falls back
        # to the shared DOWNLOAD_DIR when a per-type override isn't set, so
        # single-drive setups keep working unchanged.
        if media_type == "tv" and self.download_dir_tv:
            return self.download_dir_tv

        if media_type == "movie" and self.download_dir_movies:
            return self.download_dir_movies

        return self.download_dir

    def all_download_dirs(self) -> list[str]:
        return [
            d for d in (
                self.download_dir, self.download_dir_movies, self.download_dir_tv,
            )
            if d
        ]

    def validate(self, require_users: bool = False) -> None:
        problems = []

        if not self.api_id or not self.api_hash:
            problems.append(
                "TELEGRAM_API_ID / TELEGRAM_API_HASH are missing. Get them "
                "from https://my.telegram.org (API development tools) and "
                "put them in your .env file."
            )

        if require_users and not self.allowed_users:
            problems.append(
                "ALLOWED_USERS is empty, so every message would be ignored. "
                "Message https://t.me/userinfobot on Telegram to get your "
                "numeric user ID and set ALLOWED_USERS=<that id> in .env."
            )

        if problems:
            raise ValueError("\n".join(f"- {p}" for p in problems))


def _parse_users(raw: str) -> list[int]:
    users = []

    for user_id in raw.split(","):
        user_id = user_id.strip()

        if not user_id:
            continue

        try:
            users.append(int(user_id))
        except ValueError:
            continue

    return users

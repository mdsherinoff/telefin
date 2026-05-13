import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, events

from utils.sonarr import trigger_sonarr_scan
from utils.radarr import trigger_radarr_scan
from utils.telegram_helpers import (
    load_allowed_users,
    is_allowed_user,
    is_tv_show,
    setup_logging,
    ensure_directory,
)

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/srv/media/incoming")

# --------------------------------------------------
# Setup
# --------------------------------------------------

setup_logging()
logger = logging.getLogger(__name__)
ensure_directory(DOWNLOAD_DIR)
ALLOWED_USERS = load_allowed_users()

# --------------------------------------------------
# Allowed extensions
# --------------------------------------------------

ALLOWED_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov",
    ".wmv", ".flv", ".webm", ".m4v",
}

# --------------------------------------------------
# Telethon client
# --------------------------------------------------

client = TelegramClient("userbot_session", API_ID, API_HASH)

# --------------------------------------------------
# Handler
# --------------------------------------------------

@client.on(events.NewMessage(chats='me'))
async def handle_media(event):

    sender = await event.get_sender()

    if not sender:
        return

    if not is_allowed_user(sender.id, ALLOWED_USERS):
        return

    if not event.message.media:
        return

    # --------------------------------------------------
    # Get filename from media attributes
    # --------------------------------------------------

    filename = None

    if hasattr(event.message.media, "document"):
        for attr in event.message.media.document.attributes:
            if hasattr(attr, "file_name"):
                filename = attr.file_name
                break

    if not filename:
        logger.info("No filename found, skipping")
        return

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        await event.reply(
            f"Unsupported file type: `{extension}`\n\n"
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            parse_mode="md"
        )
        return

    # --------------------------------------------------
    # Download
    # --------------------------------------------------

    status = await event.reply(
        f"Downloading `{filename}`...",
        parse_mode="md"
    )

    try:

        destination_path = os.path.join(DOWNLOAD_DIR, filename)

        await client.download_media(
            event.message,
            file=destination_path,
        )

        # --------------------------------------------------
        # Trigger Sonarr or Radarr
        # --------------------------------------------------

        sonarr_ok = False
        radarr_ok = False

        if is_tv_show(filename):
            media_type = "TV Show"
            sonarr_ok = trigger_sonarr_scan(destination_path)
        else:
            media_type = "Movie"
            radarr_ok = trigger_radarr_scan(destination_path)

        scan_result = (
            "Sonarr notified" if sonarr_ok
            else "Radarr notified" if radarr_ok
            else "Scan trigger failed"
        )

        await status.edit(
            f"Download complete\n\n"
            f"Type: {media_type}\n"
            f"File: `{filename}`\n"
            f"Path: `{destination_path}`\n\n"
            f"{scan_result}",
            parse_mode="md"
        )

    except Exception as e:
        logger.error(f"Download failed: {e}")
        await status.edit(f"Download failed\n\n`{str(e)}`", parse_mode="md")

# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    if not API_ID or not API_HASH:
        raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH missing from .env")

    print("Userbot starting...")

    with client:
        client.run_until_disconnected()


if __name__ == "__main__":
    main()
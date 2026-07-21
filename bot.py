import logging
from pathlib import Path
from telethon import TelegramClient, events

import db
from config import Config
from db import Database
from worker import DownloadQueue, Job
from utils.telegram_helpers import (
    detect_media_type,
    is_allowed_user,
    safe_destination,
)

logger = logging.getLogger(__name__)


def build_client(config: Config) -> TelegramClient:
    # Create Telethon userbot client from configuration
    return TelegramClient(config.session_name, config.api_id, config.api_hash)


def _extract_filename(message) -> str | None:
    # Pull original filename out of media document
    media = message.media

    if not media or not hasattr(media, "document"):
        return None

    for attr in media.document.attributes:
        if hasattr(attr, "file_name") and attr.file_name:
            return attr.file_name

    return None


def register_handlers(
    client: TelegramClient,
    config: Config,
    database: Database,
    queue: DownloadQueue,
) -> None:

    @client.on(events.NewMessage(chats=config.watch_chats))
    async def handle_media(event) -> None:
        sender = await event.get_sender()

        if not sender or not is_allowed_user(sender.id, config.allowed_users):
            return

        if not event.message.media:
            return

        filename = _extract_filename(event.message)

        if not filename:
            logger.info("No filename found, skipping")
            return

        extension = Path(filename).suffix.lower()

        if extension not in config.allowed_extensions:
            await event.reply(
                f"Unsupported file type: `{extension}`\n\n"
                f"Allowed: {', '.join(sorted(config.allowed_extensions))}",
                parse_mode="md",
            )
            return

        media_type = detect_media_type(filename)
        download_dir = config.download_dir_for(media_type)
        safe_name, dest_path = safe_destination(download_dir, filename)
        size = _document_size(event.message)

        # Skip duplicates
        duplicate = await database.find_completed_duplicate(safe_name, size, media_type)

        if duplicate:
            await database.create_download(
                filename=filename,
                safe_filename=safe_name,
                media_type=media_type,
                dest_path=dest_path,
                sender_id=sender.id,
                chat_id=event.chat_id,
                message_id=event.message.id,
                status=db.STATUS_SKIPPED,
                size=size,
            )
            await event.reply(
                f"↩`{filename}` was already downloaded, skipping.",
                parse_mode="md",
            )
            return

        record = await database.create_download(
            filename=filename,
            safe_filename=safe_name,
            media_type=media_type,
            dest_path=dest_path,
            sender_id=sender.id,
            chat_id=event.chat_id,
            message_id=event.message.id,
            size=size,
        )

        status = await event.reply(
            f"Queued `{filename}`",
            parse_mode="md",
        )

        await queue.enqueue(Job(record["id"], status))

    logger.info("Handlers registered on chat(s): %s", config.watch_chats)

def _document_size(message) -> int:
    media = message.media

    if media and hasattr(media, "document") and media.document:
        return getattr(media.document, "size", 0) or 0

    return 0

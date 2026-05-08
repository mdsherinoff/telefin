import os
from pathlib import Path
from dotenv import load_dotenv

from utils.sonarr import trigger_sonarr_scan
from utils.radarr import trigger_radarr_scan
from utils.telegram_helpers import is_tv_show

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from utils.telegram_helpers import (
    load_allowed_users,
    is_allowed_user,
    reject_unauthorized_user,
    sanitize_filename,
    ensure_directory,
    setup_logging,
)

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/mnt/incoming")

# --------------------------------------------------
# Setup logging
# --------------------------------------------------

setup_logging()

# --------------------------------------------------
# Allowed users
# --------------------------------------------------

ALLOWED_USERS = load_allowed_users()

# --------------------------------------------------
# Allowed media extensions
# --------------------------------------------------

ALLOWED_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
}

# --------------------------------------------------
# Ensure download directory exists
# --------------------------------------------------

ensure_directory(DOWNLOAD_DIR)

# --------------------------------------------------
# Media handler
# --------------------------------------------------

async def handle_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    # ----------------------------------------------
    # Safety checks
    # ----------------------------------------------

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    # ----------------------------------------------
    # Allowed users only
    # ----------------------------------------------

    if not is_allowed_user(user.id, ALLOWED_USERS):
        await reject_unauthorized_user(update)
        return

    # ----------------------------------------------
    # Telegram document
    # ----------------------------------------------

    document = update.message.document

    if not document:
        return

    filename = document.file_name or "unknown_file"

    filename = sanitize_filename(filename)

    extension = Path(filename).suffix.lower()

    # ----------------------------------------------
    # Validate extension
    # ----------------------------------------------

    if extension not in ALLOWED_EXTENSIONS:

        await update.message.reply_text(
            (
                "Unsupported file type\n\n"
                f"Allowed formats:\n"
                f"{', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        )

        return

    # ----------------------------------------------
    # Download start message
    # ----------------------------------------------

    status_message = await update.message.reply_text(
        f"⬇Downloading `{filename}`...",
        parse_mode="Markdown"
    )

    try:

        # ------------------------------------------
        # Get Telegram file
        # ------------------------------------------

        telegram_file = await document.get_file()

        # ------------------------------------------
        # Destination path
        # ------------------------------------------

        destination_path = os.path.join(
            DOWNLOAD_DIR,
            filename
        )

        # ------------------------------------------
        # Download file
        # ------------------------------------------

        await telegram_file.download_to_drive(
            custom_path=destination_path
        )

        # ------------------------------------------
        # Success message
        # ------------------------------------------

        # await status_message.edit_text(
        #     (
        #         f"Download complete\n\n"
        #         f"File: {filename}\n"
        #         f"Saved to:\n"
        #         f"`{destination_path}`"
        #     ),
        #     parse_mode="Markdown"
        # )
        
        # ------------------------------------------
        # Trigger Sonarr/Radarr scans
        # ------------------------------------------

        # ------------------------------------------
        # Detect media type
        # ------------------------------------------

        if is_tv_show(filename):

            media_type = "TV Show"

            sonarr_ok = trigger_sonarr_scan(destination_path)

            scan_result = (
                "✅ Sonarr notified"
                if sonarr_ok
                else "❌ Sonarr failed"
            )

        else:

            media_type = "Movie"

            radarr_ok = trigger_radarr_scan(destination_path)

            scan_result = (
                "✅ Radarr notified"
                if radarr_ok
                else "❌ Radarr failed"
            )

        scan_results = []

        if sonarr_ok:
            scan_results.append("✅ Sonarr notified")
        else:
            scan_results.append("❌ Sonarr failed")

        if radarr_ok:
            scan_results.append("✅ Radarr notified")
        else:
            scan_results.append("❌ Radarr failed")

        # ------------------------------------------
        # Final status message
        # ------------------------------------------

        await status_message.edit_text(
        (
            f"✅ Download complete\n\n"
            f"🎬 Type: {media_type}\n"
            f"📁 File: {filename}\n"
            f"📂 Saved to:\n"
            f"`{destination_path}`\n\n"
            f"{scan_result}"
        ),
        parse_mode="Markdown"
    )

    except Exception as e:

        await status_message.edit_text(
            (
                "Download failed\n\n"
                f"`{str(e)}`"
            ),
            parse_mode="Markdown"
        )

# --------------------------------------------------
# Main
# --------------------------------------------------

def main() -> None:

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_media
        )
    )

    print("Bot is running...")

    app.run_polling()

# --------------------------------------------------

if __name__ == "__main__":
    main()
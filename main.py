import asyncio
import logging
import sys
import uvicorn

from bot import build_client, register_handlers
from config import Config
from db import Database
from events import EventBus
from utils.telegram_helpers import cleanup_orphaned_partials, ensure_directory, setup_logging
from webapp import create_app
from worker import DownloadQueue

logger = logging.getLogger(__name__)

async def run() -> None:
    setup_logging()

    config = Config.from_env()

    try:
        config.validate(require_users=True)
    except ValueError as e:
        print("\nConfiguration problem(s) found in .env:\n")
        print(e)
        print("\nFix the above and start TeleFin again.\n")
        sys.exit(1)

    for path in config.all_download_dirs():
        ensure_directory(path)

    removed_partials = cleanup_orphaned_partials(config.all_download_dirs())
    if removed_partials:
        logger.info("Removed %d orphaned .part file(s) from a previous crash", removed_partials)

    database = Database(config.db_path)
    await database.connect()

    interrupted = await database.reset_interrupted()
    if interrupted:
        logger.info("Reset %d interrupted download(s) to failed", len(interrupted))

    bus = EventBus()

    client = build_client(config)
    print("Userbot starting...")
    await client.start()

    queue = DownloadQueue(client, database, bus, config)
    queue.start()

    register_handlers(client, config, database, queue)

    tasks = [asyncio.create_task(client.run_until_disconnected())]

    if config.web_enabled:
        app = create_app(config, database, bus, queue)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.web_host,
                port=config.web_port,
                log_level="info",
                loop="asyncio",
            )
        )
        host_hint = (
            "localhost"
            if config.web_host in ("0.0.0.0", "::")
            else config.web_host
        )
        logger.info(
            "Web dashboard: http://%s:%d "
            "(from another machine use your server's IP)",
            host_hint,
            config.web_port,
        )
        tasks.append(asyncio.create_task(server.serve()))

    try:
        await asyncio.gather(*tasks)
    finally:
        await queue.stop()
        await database.close()

def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    main()

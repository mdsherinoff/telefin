import asyncio

from bot import build_client
from config import Config
from utils.telegram_helpers import setup_logging


async def run() -> None:
    setup_logging()

    config = Config.from_env()
    config.validate()

    client = build_client(config)

    print("Starting Telegram login...")
    await client.start()

    me = await client.get_me()
    print(f"Signed in successfully as {me.first_name}. Session saved.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(run())

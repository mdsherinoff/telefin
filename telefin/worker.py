import asyncio
import logging
import os
import time
from dataclasses import dataclass

import db
from config import Config
from db import Database
from events import EventBus
from utils.radarr import trigger_radarr_scan
from utils.sonarr import trigger_sonarr_scan
from utils.telegram_helpers import (
    format_size,
    format_speed,
    make_progress_bar,
)

logger = logging.getLogger(__name__)


@dataclass
class Job:
    # A unit of work handed to a worker: which record to process, and the
    # Telegram status message to keep editing (None for web-triggered retries).
    download_id: int
    status_message: object | None = None


class DownloadQueue:
    # Owns the asyncio queue and a pool of workers that download files one
    # (or a few) at a time, update the database, edit the Telegram status
    # message, and broadcast progress to the web dashboard.

    def __init__(
        self,
        client,
        database: Database,
        bus: EventBus,
        config: Config,
    ) -> None:
        self.client = client
        self.db = database
        self.bus = bus
        self.config = config

        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []

    # lifecycle
    def start(self) -> None:
        count = max(1, self.config.max_concurrent_downloads)

        for index in range(count):
            task = asyncio.create_task(self._run_worker(index))
            self._workers.append(task)

        logger.info("Started %d download worker(s)", count)

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()

    async def enqueue(self, job: Job) -> None:
        await self._queue.put(job)
        await self._publish(job.download_id, "queued")

    # worker loop
    async def _run_worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()

            try:
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Worker %d crashed on job %s", index, job)
                await self._fail(job, str(e))
            finally:
                self._queue.task_done()

    async def _process(self, job: Job) -> None:
        record = await self.db.get_download(job.download_id)

        if not record:
            logger.warning("Job %s has no record, skipping", job.download_id)
            return

        message = await self._resolve_source_message(record)

        if message is None:
            await self._fail(job, "Source message is no longer available")
            return

        status = job.status_message
        await self.db.update_download(
            record["id"],
            status=db.STATUS_DOWNLOADING,
            started_at=_now_iso(),
            error=None,
        )
        await self._publish(record["id"], "downloading")
        await self._edit(status, f"⬇️ Downloading `{record['filename']}`...")

        tracker = _ProgressTracker(self.config.progress_interval)

        async def on_progress(current: int, total: int) -> None:
            await self._on_progress(record, status, tracker, current, total)

        dest_path = record["dest_path"]

        await self.client.download_media(
            message,
            file=dest_path,
            progress_callback=on_progress,
        )

        size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
        await self.db.update_download(
            record["id"],
            status=db.STATUS_IMPORTING,
            downloaded=size,
            size=size or record["size"],
        )
        await self._publish(record["id"], "importing")

        arr_result = await self._trigger_arr(record["media_type"], dest_path)

        await self.db.update_download(
            record["id"],
            status=db.STATUS_COMPLETED,
            arr_result=arr_result,
            completed_at=_now_iso(),
        )
        await self._publish(record["id"], "completed")

        await self._edit(
            status,
            f"✅ Download complete\n\n"
            f"Type: {_media_label(record['media_type'])}\n"
            f"File: `{record['filename']}`\n"
            f"Size: {format_size(size)}\n"
            f"Path: `{dest_path}`\n\n"
            f"{arr_result}",
        )

    # helpers
    async def _resolve_source_message(self, record: dict):
        # For a fresh forward the message is reachable; for a retry we look it
        # up again from Telegram, which may fail if the user deleted it.
        try:
            return await self.client.get_messages(
                record["chat_id"],
                ids=record["message_id"],
            )
        except Exception as e:
            logger.error("Could not fetch source message: %s", e)
            return None

    async def _on_progress(
        self,
        record: dict,
        status,
        tracker: "_ProgressTracker",
        current: int,
        total: int,
    ) -> None:
        if not tracker.should_update(current):
            return

        speed = tracker.speed(current)
        fraction = (current / total) if total else 0.0

        await self.db.update_download(
            record["id"],
            downloaded=current,
            size=total or record["size"],
        )

        await self.bus.publish({
            "type": "progress",
            "id": record["id"],
            "downloaded": current,
            "size": total,
            "speed": speed,
        })

        bar = make_progress_bar(fraction)
        percent = int(fraction * 100)

        await self._edit(
            status,
            f"⬇️ Downloading `{record['filename']}`\n\n"
            f"{bar} {percent}%\n"
            f"{format_size(current)} / {format_size(total)}"
            f" • {format_speed(speed)}",
        )

    async def _trigger_arr(self, media_type: str, path: str) -> str:
        if media_type == "tv":
            ok = await trigger_sonarr_scan(path)
            return "Sonarr notified" if ok else "Sonarr scan failed"

        ok = await trigger_radarr_scan(path)
        return "Radarr notified" if ok else "Radarr scan failed"

    async def _fail(self, job: Job, error: str) -> None:
        await self.db.update_download(
            job.download_id,
            status=db.STATUS_FAILED,
            error=error,
            completed_at=_now_iso(),
        )
        await self._publish(job.download_id, "failed")
        await self._edit(job.status_message, f"Download failed\n\n`{error}`")

    async def _edit(self, message, text: str) -> None:
        if message is None:
            return

        try:
            await message.edit(text, parse_mode="md")
        except Exception:
            # Ignore "message not modified" and transient edit failures.
            pass

    async def _publish(self, download_id: int, status: str) -> None:
        record = await self.db.get_download(download_id)

        if record:
            await self.bus.publish({
                "type": "status",
                "status": status,
                "download": record,
            })


class _ProgressTracker:
    # Throttles updates and estimates transfer speed between samples.

    def __init__(self, interval: int) -> None:
        self.interval = max(1, interval)
        self._last_time = time.monotonic()
        self._last_bytes = 0
        self._speed = 0.0

    def should_update(self, current: int) -> bool:
        now = time.monotonic()

        if now - self._last_time < self.interval:
            return False

        elapsed = now - self._last_time

        if elapsed > 0:
            self._speed = (current - self._last_bytes) / elapsed

        self._last_time = now
        self._last_bytes = current
        return True

    def speed(self, current: int) -> float:
        return max(0.0, self._speed)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _media_label(media_type: str) -> str:
    return "TV Show" if media_type == "tv" else "Movie"

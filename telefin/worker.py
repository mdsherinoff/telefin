import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass

from telethon.errors import FloodWaitError

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


class DownloadCancelled(Exception):
    # Raised from inside the Telethon progress_callback to abort an
    # in-flight download when the user deletes it from the web dashboard.
    pass


@dataclass
class Job:
    # A unit of work handed to a worker: which record to process, and the
    # Telegram status message to keep editing (None for web-triggered retries).
    download_id: int
    status_message: object | None = None
    attempt: int = 0


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
        self._cancel_requested: set[int] = set()

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

    def cancel(self, download_id: int) -> None:
        # Interrupts an in-flight download_media() call by having the
        # progress callback raise on its next tick. _run_worker persists
        # the resulting status once the download actually aborts.
        self._cancel_requested.add(download_id)

    async def cancel_queued(self, download_id: int) -> bool:
        # Cancels a job that hasn't started downloading yet, preserving its
        # history (unlike delete, which removes the row entirely). Marking
        # it here relies on _process re-checking the status is still QUEUED
        # once dequeued, so the stale Job sitting in self._queue is skipped
        # rather than processed.
        record = await self.db.get_download(download_id)

        if not record or record["status"] != db.STATUS_QUEUED:
            return False

        await self.db.update_download(
            download_id,
            status=db.STATUS_CANCELLED,
            error="Cancelled by user",
            completed_at=_now_iso(),
        )
        await self._publish(download_id, "cancelled")
        return True

    # worker loop
    async def _run_worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()

            try:
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except DownloadCancelled:
                logger.info("Job %s cancelled", job.download_id)
                await self.db.update_download(
                    job.download_id,
                    status=db.STATUS_CANCELLED,
                    error="Cancelled by user",
                    completed_at=_now_iso(),
                )
                await self._publish(job.download_id, "cancelled")
                await self._edit(job.status_message, "Download cancelled")
            except FloodWaitError as e:
                await self._retry_after_flood_wait(job, e)
            except Exception as e:
                logger.exception("Worker %d crashed on job %s", index, job)

                if job.attempt < self.config.max_download_retries:
                    await self._retry_after_backoff(job, e)
                else:
                    await self._fail(job, str(e))
            finally:
                self._cancel_requested.discard(job.download_id)
                self._queue.task_done()

    async def _retry_after_backoff(self, job: Job, error: Exception) -> None:
        delay = self.config.retry_backoff_seconds * (2 ** job.attempt)
        next_job = Job(job.download_id, job.status_message, job.attempt + 1)

        logger.info(
            "Retrying job %s in %ds (attempt %d/%d) after: %s",
            job.download_id, delay, next_job.attempt,
            self.config.max_download_retries, error,
        )

        await self.db.update_download(
            job.download_id,
            status=db.STATUS_QUEUED,
            error=f"Retrying after error: {error}",
        )
        await self._publish(job.download_id, "queued")
        await self._edit(
            job.status_message,
            f"Download failed, retrying in {delay}s "
            f"(attempt {next_job.attempt}/{self.config.max_download_retries})\n\n"
            f"`{error}`",
        )

        await asyncio.sleep(delay)
        await self._queue.put(next_job)

    async def _retry_after_flood_wait(self, job: Job, error: FloodWaitError) -> None:
        # Telegram tells us exactly how long to back off; this doesn't
        # count against max_download_retries (it's rate limiting, not a
        # failure) and the job keeps its original attempt count.
        delay = error.seconds + 1

        logger.warning(
            "Job %s hit a Telegram flood-wait, retrying in %ds",
            job.download_id, delay,
        )

        await self.db.update_download(
            job.download_id,
            status=db.STATUS_QUEUED,
            error=f"Waiting on Telegram rate limit ({delay}s)",
        )
        await self._publish(job.download_id, "queued")
        await self._edit(
            job.status_message,
            f"Telegram rate limit hit, retrying in {delay}s...",
        )

        await asyncio.sleep(delay)
        await self._queue.put(job)

    async def _process(self, job: Job) -> None:
        record = await self.db.get_download(job.download_id)

        if not record:
            logger.warning("Job %s has no record, skipping", job.download_id)
            return

        if record["status"] != db.STATUS_QUEUED:
            logger.info(
                "Job %s no longer queued (status=%s), skipping",
                job.download_id, record["status"],
            )
            return

        message = await self._resolve_source_message(record)

        if message is None:
            await self._fail(job, "Source message is no longer available")
            return

        space_error = self._check_disk_space(record)

        if space_error:
            await self._fail(job, space_error)
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
        tmp_path = dest_path + ".part"

        try:
            await self.client.download_media(
                message,
                file=tmp_path,
                progress_callback=on_progress,
            )
            os.replace(tmp_path, dest_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

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
    def _check_disk_space(self, record: dict) -> str | None:
        # record["size"] is 0 when Telegram didn't report a document size
        # up front; nothing to compare against, so let the download proceed.
        expected = record["size"]

        if not expected:
            return None

        try:
            free = shutil.disk_usage(os.path.dirname(record["dest_path"])).free
        except OSError as e:
            logger.warning("Could not check free disk space: %s", e)
            return None

        if free < expected:
            return (
                f"Not enough disk space: need {format_size(expected)}, "
                f"only {format_size(free)} free"
            )

        return None

    async def _resolve_source_message(self, record: dict):
        # For a fresh forward the message is reachable; for a retry we look it
        # up again from Telegram, which may fail if the user deleted it.
        try:
            return await self.client.get_messages(
                record["chat_id"],
                ids=record["message_id"],
            )
        except FloodWaitError:
            # Transient rate limiting, not "message gone" -- let it bubble
            # up to _run_worker's flood-wait handling instead of failing
            # the download outright.
            raise
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
        if record["id"] in self._cancel_requested:
            raise DownloadCancelled(f"Download {record['id']} cancelled")

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
            ok = await trigger_sonarr_scan(
                path, self.config.sonarr_url, self.config.sonarr_api_key
            )
            return "Sonarr notified" if ok else "Sonarr scan failed"

        ok = await trigger_radarr_scan(
            path, self.config.radarr_url, self.config.radarr_api_key
        )
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

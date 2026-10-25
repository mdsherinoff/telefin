import asyncio
import itertools
import logging
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime

from telethon.errors import FloodWaitError

import db
from config import Config
from db import Database
from events import EventBus
from utils.arr_status import fetch_imported_paths
from utils.radarr import trigger_radarr_scan
from utils.schedule import in_window
from utils.sonarr import trigger_sonarr_scan
from utils.telegram_helpers import (
    format_size,
    format_speed,
    make_progress_bar,
)

logger = logging.getLogger(__name__)

# How often to re-check whether the queue was resumed / the download window
# opened, and how often to look for completed imports.
GATE_POLL_SECONDS = 30
IMPORT_CHECK_SECONDS = 120


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

        # Entries are (rank, seq, job): promoted jobs (rank 0) run before
        # normal ones (rank 1); seq keeps FIFO order within a rank.
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._pending_jobs: dict[int, Job] = {}
        self._paused = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._import_task: asyncio.Task | None = None
        self._workers: list[asyncio.Task] = []
        self._cancel_requested: set[int] = set()
        self._notify_task: asyncio.Task | None = None
        self._retention_task: asyncio.Task | None = None

    # lifecycle
    def start(self) -> None:
        count = max(1, self.config.max_concurrent_downloads)

        for index in range(count):
            task = asyncio.create_task(self._run_worker(index))
            self._workers.append(task)

        logger.info("Started %d download worker(s)", count)

        if self.config.notify_interval_minutes > 0:
            self._notify_task = asyncio.create_task(self._run_periodic_notify())
            logger.info(
                "Re-notifying Sonarr/Radarr about pending files every %d minute(s)",
                self.config.notify_interval_minutes,
            )

        self._import_task = asyncio.create_task(self._run_import_checker())

        if self.config.retention_days > 0:
            self._retention_task = asyncio.create_task(self._run_periodic_retention())
            logger.info(
                "Pruning download history older than %d day(s) daily",
                self.config.retention_days,
            )

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()

        if self._notify_task:
            self._notify_task.cancel()

        if self._retention_task:
            self._retention_task.cancel()

        if self._import_task:
            self._import_task.cancel()

    async def enqueue(self, job: Job) -> None:
        self._put(job)
        await self._publish(job.download_id, "queued")

    def _put(self, job: Job, promoted: bool = False) -> None:
        self._pending_jobs[job.download_id] = job
        self._queue.put_nowait((0 if promoted else 1, next(self._seq), job))

    # pause / schedule
    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        # Only gates *starting* jobs; a download already in flight finishes.
        self._paused = True
        self._resume_event.clear()
        self._broadcast_state()

    def resume(self) -> None:
        self._paused = False
        self._resume_event.set()
        self._broadcast_state()

    def in_download_window(self) -> bool:
        return in_window(
            datetime.now().time(),
            self.config.download_window_start,
            self.config.download_window_end,
        )

    def state(self) -> dict:
        return {
            "paused": self._paused,
            "in_window": self.in_download_window(),
            "window_start": self.config.download_window_start,
            "window_end": self.config.download_window_end,
            "speed_limit_kbps": self.config.max_download_speed_kbps,
        }

    def _broadcast_state(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        loop.create_task(self.bus.publish({"type": "queue", **self.state()}))

    async def _wait_until_allowed(self) -> None:
        while self._paused or not self.in_download_window():
            if self._paused:
                await self._resume_event.wait()
            else:
                await asyncio.sleep(GATE_POLL_SECONDS)

    async def promote(self, download_id: int) -> bool:
        # Moves a queued download to the front. The original queue entry is
        # left in place and skipped later by _process, which only runs jobs
        # that are still STATUS_QUEUED.
        record = await self.db.get_download(download_id)

        if not record or record["status"] != db.STATUS_QUEUED:
            return False

        await self.db.promote_download(download_id)
        job = self._pending_jobs.get(download_id) or Job(download_id)
        self._put(job, promoted=True)
        await self._publish(download_id, "queued")
        return True

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

    async def renotify(self, download_id: int) -> str:
        # The Sonarr/Radarr scan command is fire-and-forget: if the title
        # wasn't requested through Seerr, the *arr app just ignores it and
        # the file sits in the incoming folder untouched. Re-triggering the
        # scan is what lets a later Seerr request pick it up without
        # restarting telefin. Raises LookupError (record missing) or
        # ValueError (not eligible) for the caller to translate into an
        # HTTP status.
        record = await self.db.get_download(download_id)

        if not record:
            raise LookupError(f"Download {download_id} not found")

        if record["status"] != db.STATUS_COMPLETED:
            raise ValueError(f"Cannot notify a {record['status']} download")

        dest_path = record["dest_path"]

        if not dest_path or not os.path.exists(dest_path):
            raise ValueError(
                "File is no longer at the download path "
                "(already imported, or removed)"
            )

        arr_result = await self._trigger_arr(record["media_type"], dest_path)
        await self.db.update_download(
            download_id, arr_result=arr_result, import_status="pending"
        )
        await self._publish(download_id, "completed")
        return arr_result

    async def _run_periodic_notify(self) -> None:
        interval = self.config.notify_interval_minutes * 60

        while True:
            try:
                await asyncio.sleep(interval)
                await self._renotify_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Periodic Sonarr/Radarr re-notify sweep failed")

    async def _renotify_pending(self) -> None:
        # Completed downloads whose file is still sitting at dest_path
        # haven't been imported by Sonarr/Radarr yet (a successful import
        # moves the file out), so re-announce just those.
        records = await self.db.list_downloads(status=db.STATUS_COMPLETED, limit=1000)
        pending = [
            r for r in records
            if r["dest_path"]
            and os.path.exists(r["dest_path"])
            and r.get("import_status") != "imported"
        ]

        if not pending:
            return

        logger.info(
            "Re-notifying Sonarr/Radarr about %d file(s) still pending import",
            len(pending),
        )

        for record in pending:
            try:
                arr_result = await self._trigger_arr(
                    record["media_type"], record["dest_path"]
                )
                await self.db.update_download(
                    record["id"], arr_result=arr_result, import_status="pending"
                )
                await self._publish(record["id"], "completed")
            except Exception as e:
                logger.warning("Re-notify failed for %s: %s", record["id"], e)

    async def _run_import_checker(self) -> None:
        while True:
            try:
                await asyncio.sleep(IMPORT_CHECK_SECONDS)
                await self._check_imports()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Import status sweep failed")

    async def _check_imports(self) -> None:
        # A completed download is "imported" once Sonarr/Radarr report it in
        # their history (covers copy/hardlink imports that leave the file in
        # place) or the file has left dest_path (a plain move).
        records = await self.db.list_downloads(status=db.STATUS_COMPLETED, limit=1000)
        waiting = [r for r in records if r.get("import_status") != "imported"]

        if not waiting:
            return

        history: dict[str, set[str] | None] = {}

        for record in waiting:
            media_type = record["media_type"]

            if media_type not in history:
                if media_type == "tv":
                    url, key = self.config.sonarr_url, self.config.sonarr_api_key
                else:
                    url, key = self.config.radarr_url, self.config.radarr_api_key

                history[media_type] = await fetch_imported_paths(url, key)

            imported_paths = history[media_type]
            dest_path = record["dest_path"]
            imported = (
                (imported_paths is not None and dest_path in imported_paths)
                or not dest_path
                or not os.path.exists(dest_path)
            )
            new_status = "imported" if imported else "pending"

            if new_status != record.get("import_status"):
                await self.db.update_download(record["id"], import_status=new_status)
                await self._publish(record["id"], "completed")

    async def _run_periodic_retention(self) -> None:
        while True:
            try:
                removed = await self.db.delete_old_downloads(self.config.retention_days)
                if removed:
                    logger.info(
                        "Pruned %d old download record(s) (retention: %d day(s))",
                        removed, self.config.retention_days,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Retention sweep failed")

            await asyncio.sleep(24 * 3600)

    # worker loop
    async def _run_worker(self, index: int) -> None:
        while True:
            await self._wait_until_allowed()
            _, _, job = await self._queue.get()

            if self._pending_jobs.get(job.download_id) is job:
                del self._pending_jobs[job.download_id]

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
        self._put(next_job)

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
        self._put(job)

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
            import_status="pending",
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

        delay = tracker.throttle_delay(
            current, self.config.max_download_speed_kbps * 1024
        )

        if delay > 0:
            await asyncio.sleep(delay)

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
        self._started = self._last_time

    def throttle_delay(self, current: int, limit_bytes_per_sec: int) -> float:
        # Seconds to sleep so the average rate since this download began
        # stays at or below the limit. 0 means unlimited. Applied per
        # download, so total bandwidth is limit * concurrent downloads.
        if limit_bytes_per_sec <= 0:
            return 0.0

        elapsed = time.monotonic() - self._started
        return max(0.0, current / limit_bytes_per_sec - elapsed)

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

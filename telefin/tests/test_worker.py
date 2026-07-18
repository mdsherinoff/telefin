import asyncio

from telethon.errors import FloodWaitError

import db
from events import EventBus
from tests.factories import make_config
from worker import DownloadQueue, Job


class FakeDatabase:
    # Minimal in-memory stand-in for db.Database, just enough of the
    # interface DownloadQueue.cancel_queued() touches.

    def __init__(self):
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    def add(self, **fields) -> dict:
        row_id = self._next_id
        self._next_id += 1
        row = {"id": row_id, **fields}
        self._rows[row_id] = row
        return row

    async def get_download(self, download_id: int) -> dict | None:
        row = self._rows.get(download_id)
        return dict(row) if row else None

    async def update_download(self, download_id: int, **fields) -> None:
        if download_id in self._rows:
            self._rows[download_id].update(fields)


def make_queue() -> tuple[DownloadQueue, FakeDatabase]:
    fake_db = FakeDatabase()
    queue = DownloadQueue(client=None, database=fake_db, bus=EventBus(), config=make_config())
    return queue, fake_db


class TestCancelQueued:
    def test_cancels_a_queued_job(self):
        queue, fake_db = make_queue()
        record = fake_db.add(status=db.STATUS_QUEUED, filename="movie.mkv")

        cancelled = asyncio.run(queue.cancel_queued(record["id"]))

        assert cancelled is True
        stored = fake_db._rows[record["id"]]
        assert stored["status"] == db.STATUS_CANCELLED
        assert stored["error"] == "Cancelled by user"

    def test_refuses_when_not_queued(self):
        queue, fake_db = make_queue()
        record = fake_db.add(status=db.STATUS_DOWNLOADING, filename="movie.mkv")

        cancelled = asyncio.run(queue.cancel_queued(record["id"]))

        assert cancelled is False
        assert fake_db._rows[record["id"]]["status"] == db.STATUS_DOWNLOADING

    def test_refuses_when_missing(self):
        queue, _ = make_queue()

        cancelled = asyncio.run(queue.cancel_queued(999))

        assert cancelled is False


class TestCancelSignal:
    def test_marks_download_id_for_in_flight_cancellation(self):
        queue, _ = make_queue()

        queue.cancel(42)

        assert 42 in queue._cancel_requested


class TestFloodWaitRetry:
    def test_requeues_without_burning_a_retry_attempt(self):
        queue, fake_db = make_queue()
        record = fake_db.add(status=db.STATUS_DOWNLOADING, filename="movie.mkv")
        job = Job(record["id"], status_message=None, attempt=1)
        error = FloodWaitError(request=None, capture=1)

        asyncio.run(queue._retry_after_flood_wait(job, error))

        assert fake_db._rows[record["id"]]["status"] == db.STATUS_QUEUED
        requeued = queue._queue.get_nowait()
        assert requeued.download_id == record["id"]
        assert requeued.attempt == 1  # unchanged -- flood-wait isn't a failure

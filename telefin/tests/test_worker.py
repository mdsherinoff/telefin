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

    async def list_downloads(self, status: str | None = None, **_ignored) -> list[dict]:
        rows = self._rows.values()
        if status is not None:
            rows = [r for r in rows if r["status"] == status]
        return [dict(r) for r in rows]


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


class TestRenotify:
    def test_raises_lookup_error_when_missing(self):
        queue, _ = make_queue()

        try:
            asyncio.run(queue.renotify(999))
            assert False, "expected LookupError"
        except LookupError:
            pass

    def test_raises_value_error_when_not_completed(self):
        queue, fake_db = make_queue()
        record = fake_db.add(status=db.STATUS_QUEUED, filename="movie.mkv", dest_path="/x")

        try:
            asyncio.run(queue.renotify(record["id"]))
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_raises_value_error_when_file_missing(self, tmp_path):
        queue, fake_db = make_queue()
        missing = str(tmp_path / "gone.mkv")
        record = fake_db.add(
            status=db.STATUS_COMPLETED, filename="movie.mkv",
            dest_path=missing, media_type="movie",
        )

        try:
            asyncio.run(queue.renotify(record["id"]))
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_retriggers_when_file_still_present(self, tmp_path):
        queue, fake_db = make_queue()
        dest = tmp_path / "movie.mkv"
        dest.write_bytes(b"x")
        record = fake_db.add(
            status=db.STATUS_COMPLETED, filename="movie.mkv",
            dest_path=str(dest), media_type="movie", arr_result="stale",
        )

        result = asyncio.run(queue.renotify(record["id"]))

        assert result == "Radarr scan failed"  # no RADARR_URL configured in tests
        assert fake_db._rows[record["id"]]["arr_result"] == result


class TestRenotifyPending:
    def test_only_renotifies_files_still_on_disk(self, tmp_path):
        queue, fake_db = make_queue()
        present = tmp_path / "present.mkv"
        present.write_bytes(b"x")

        pending = fake_db.add(
            status=db.STATUS_COMPLETED, filename="present.mkv",
            dest_path=str(present), media_type="movie", arr_result="stale",
        )
        already_imported = fake_db.add(
            status=db.STATUS_COMPLETED, filename="gone.mkv",
            dest_path=str(tmp_path / "gone.mkv"), media_type="movie",
            arr_result="original",
        )

        asyncio.run(queue._renotify_pending())

        assert fake_db._rows[pending["id"]]["arr_result"] == "Radarr scan failed"
        assert fake_db._rows[already_imported["id"]]["arr_result"] == "original"


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

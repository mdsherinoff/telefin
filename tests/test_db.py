import asyncio
from datetime import datetime, timedelta, timezone

import db
from db import Database


def iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


async def _make_database(path: str) -> Database:
    database = Database(path)
    await database.connect()
    return database


class TestFindCompletedDuplicate:
    def test_matches_same_filename_size_and_media_type(self, tmp_path):
        async def scenario():
            database = await _make_database(str(tmp_path / "test.db"))
            await database.create_download(
                filename="movie.mkv", safe_filename="movie.mkv", media_type="movie",
                dest_path="/movies/movie.mkv", sender_id=1, chat_id=1, message_id=1,
                status=db.STATUS_COMPLETED, size=1000,
            )
            result = await database.find_completed_duplicate("movie.mkv", 1000, "movie")
            await database.close()
            return result

        result = asyncio.run(scenario())
        assert result is not None

    def test_does_not_match_across_media_types(self, tmp_path):
        # Movies and TV episodes now download to separate directories
        # (Config.download_dir_for), so an identical filename+size no
        # longer guarantees it's the same physical file -- a completed
        # movie must not shadow a same-named/same-sized TV episode.
        async def scenario():
            database = await _make_database(str(tmp_path / "test.db"))
            await database.create_download(
                filename="sample.mkv", safe_filename="sample.mkv", media_type="movie",
                dest_path="/movies/sample.mkv", sender_id=1, chat_id=1, message_id=1,
                status=db.STATUS_COMPLETED, size=500,
            )
            result = await database.find_completed_duplicate("sample.mkv", 500, "tv")
            await database.close()
            return result

        result = asyncio.run(scenario())
        assert result is None

    def test_does_not_match_different_size(self, tmp_path):
        async def scenario():
            database = await _make_database(str(tmp_path / "test.db"))
            await database.create_download(
                filename="movie.mkv", safe_filename="movie.mkv", media_type="movie",
                dest_path="/movies/movie.mkv", sender_id=1, chat_id=1, message_id=1,
                status=db.STATUS_COMPLETED, size=1000,
            )
            result = await database.find_completed_duplicate("movie.mkv", 2000, "movie")
            await database.close()
            return result

        result = asyncio.run(scenario())
        assert result is None


class TestDeleteOldDownloads:
    def test_prunes_old_terminal_records_only(self, tmp_path):
        async def scenario():
            database = await _make_database(str(tmp_path / "test.db"))

            old_completed = await database.create_download(
                filename="old.mkv", safe_filename="old.mkv", media_type="movie",
                dest_path="/x/old.mkv", sender_id=1, chat_id=1, message_id=1,
                status=db.STATUS_COMPLETED,
            )
            await database.update_download(old_completed["id"], completed_at=iso(40))

            recent_completed = await database.create_download(
                filename="recent.mkv", safe_filename="recent.mkv", media_type="movie",
                dest_path="/x/recent.mkv", sender_id=1, chat_id=1, message_id=2,
                status=db.STATUS_COMPLETED,
            )
            await database.update_download(recent_completed["id"], completed_at=iso(1))

            old_queued = await database.create_download(
                filename="still-queued.mkv", safe_filename="still-queued.mkv",
                media_type="movie", dest_path="/x/q.mkv", sender_id=1,
                chat_id=1, message_id=3, status=db.STATUS_QUEUED,
            )
            # Backdate created_at directly to simulate a long-queued item --
            # it must survive pruning regardless of age since it's not terminal.
            await database._conn.execute(
                "UPDATE downloads SET created_at = ? WHERE id = ?",
                (iso(40), old_queued["id"]),
            )
            await database._conn.commit()

            removed = await database.delete_old_downloads(days=30)

            remaining_ids = {r["id"] for r in await database.list_downloads(limit=100)}
            await database.close()
            return removed, remaining_ids, old_completed["id"], recent_completed["id"], old_queued["id"]

        removed, remaining_ids, old_id, recent_id, queued_id = asyncio.run(scenario())

        assert removed == 1
        assert old_id not in remaining_ids
        assert recent_id in remaining_ids
        assert queued_id in remaining_ids

    def test_falls_back_to_created_at_when_completed_at_missing(self, tmp_path):
        async def scenario():
            database = await _make_database(str(tmp_path / "test.db"))

            record = await database.create_download(
                filename="dup.mkv", safe_filename="dup.mkv", media_type="movie",
                dest_path="/x/dup.mkv", sender_id=1, chat_id=1, message_id=1,
                status=db.STATUS_SKIPPED,
            )
            # Skipped duplicates never get a completed_at; retention should
            # still catch them via created_at.
            await database._conn.execute(
                "UPDATE downloads SET created_at = ? WHERE id = ?",
                (iso(40), record["id"]),
            )
            await database._conn.commit()

            removed = await database.delete_old_downloads(days=30)
            remaining = await database.get_download(record["id"])
            await database.close()
            return removed, remaining

        removed, remaining = asyncio.run(scenario())

        assert removed == 1
        assert remaining is None

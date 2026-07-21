import logging
from datetime import datetime, timedelta, timezone
import aiosqlite

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_IMPORTING = "importing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"

# Statuses that are still "in flight" and should be reset on a fresh start.
NON_TERMINAL = (STATUS_QUEUED, STATUS_DOWNLOADING, STATUS_IMPORTING)

# Finished statuses eligible for retention pruning.
TERMINAL = (STATUS_COMPLETED, STATUS_FAILED, STATUS_SKIPPED, STATUS_CANCELLED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT    NOT NULL,
    safe_filename TEXT    NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    downloaded    INTEGER NOT NULL DEFAULT 0,
    status        TEXT    NOT NULL DEFAULT 'queued',
    media_type    TEXT    NOT NULL DEFAULT 'unknown',
    dest_path     TEXT,
    error         TEXT,
    arr_result    TEXT,
    sender_id     INTEGER,
    chat_id       INTEGER,
    message_id    INTEGER,
    created_at    TEXT    NOT NULL,
    started_at    TEXT,
    completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at);
"""

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

        logger.info("Database ready at %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()

    async def create_download(
        self,
        *,
        filename: str,
        safe_filename: str,
        media_type: str,
        dest_path: str,
        sender_id: int | None,
        chat_id: int | None,
        message_id: int | None,
        status: str = STATUS_QUEUED,
        size: int = 0,
    ) -> dict:
        cursor = await self._conn.execute(
            """
            INSERT INTO downloads (
                filename, safe_filename, size, status, media_type,
                dest_path, sender_id, chat_id, message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename, safe_filename, size, status, media_type,
                dest_path, sender_id, chat_id, message_id, _now(),
            ),
        )
        await self._conn.commit()

        return await self.get_download(cursor.lastrowid)

    async def update_download(self, download_id: int, **fields) -> None:
        if not fields:
            return

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values())
        values.append(download_id)

        await self._conn.execute(
            f"UPDATE downloads SET {columns} WHERE id = ?",
            values,
        )
        await self._conn.commit()

    async def get_download(self, download_id: int) -> dict | None:
        cursor = await self._conn.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        )
        row = await cursor.fetchone()

        return dict(row) if row else None

    async def list_downloads(
        self,
        status: str | None = None,
        active: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        query = "SELECT * FROM downloads"
        params: list = []
        clauses: list[str] = []

        if active:
            placeholders = ", ".join("?" for _ in NON_TERMINAL)
            clauses.append(f"status IN ({placeholders})")
            params.extend(NON_TERMINAL)
        elif status:
            clauses.append("status = ?")
            params.append(status)

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY id ASC" if active else " ORDER BY id DESC"
        query += " LIMIT ?"
        params.append(limit)

        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def find_completed_duplicate(
        self,
        safe_filename: str,
        size: int,
        media_type: str,
    ) -> dict | None:
        # media_type is part of the match: movies and TV episodes now land
        # in separate directories (see Config.download_dir_for), so an
        # identical filename+size no longer implies the same physical file
        # the way it did when everything shared one download directory.
        cursor = await self._conn.execute(
            """
            SELECT * FROM downloads
            WHERE safe_filename = ? AND status = ? AND media_type = ?
            ORDER BY id DESC LIMIT 1
            """,
            (safe_filename, STATUS_COMPLETED, media_type),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        existing = dict(row)

        if size and existing["size"] and existing["size"] != size:
            return None

        return existing

    async def reset_interrupted(self) -> list[dict]:
        placeholders = ", ".join("?" for _ in NON_TERMINAL)

        cursor = await self._conn.execute(
            f"SELECT * FROM downloads WHERE status IN ({placeholders})",
            NON_TERMINAL,
        )
        rows = [dict(row) for row in await cursor.fetchall()]

        if rows:
            await self._conn.execute(
                f"""
                UPDATE downloads
                SET status = ?, error = 'Interrupted by restart'
                WHERE status IN ({placeholders})
                """,
                (STATUS_FAILED, *NON_TERMINAL),
            )
            await self._conn.commit()

        return rows

    async def delete_download(self, download_id: int) -> dict | None:
        record = await self.get_download(download_id)

        if record:
            await self._conn.execute(
                "DELETE FROM downloads WHERE id = ?",
                (download_id,),
            )
            await self._conn.commit()

        return record

    async def delete_old_downloads(self, days: int) -> int:
        # Prunes finished (terminal-status) records older than `days`, using
        # completed_at when set and falling back to created_at for rows that
        # never got one (e.g. skipped duplicates). Doesn't touch files on
        # disk -- only the history row.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        placeholders = ", ".join("?" for _ in TERMINAL)

        cursor = await self._conn.execute(
            f"""
            DELETE FROM downloads
            WHERE status IN ({placeholders})
            AND COALESCE(completed_at, created_at) < ?
            """,
            (*TERMINAL, cutoff),
        )
        await self._conn.commit()

        return cursor.rowcount

    async def get_stats(self) -> dict:
        cursor = await self._conn.execute(
            "SELECT status, COUNT(*) AS count FROM downloads GROUP BY status"
        )
        by_status = {
            row["status"]: row["count"]
            for row in await cursor.fetchall()
        }

        cursor = await self._conn.execute(
            "SELECT COALESCE(SUM(size), 0) AS total FROM downloads "
            "WHERE status = ?",
            (STATUS_COMPLETED,),
        )
        total_row = await cursor.fetchone()

        return {
            "by_status": by_status,
            "completed": by_status.get(STATUS_COMPLETED, 0),
            "failed": by_status.get(STATUS_FAILED, 0),
            "active": sum(by_status.get(s, 0) for s in NON_TERMINAL),
            "total_bytes": total_row["total"] if total_row else 0,
        }

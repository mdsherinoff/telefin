import asyncio
import base64
import logging
import os
import re
import secrets
import shutil
from pathlib import Path

import dotenv
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

import db
from config import ENV_PATH, Config
from db import Database
from events import EventBus
from worker import DownloadQueue, Job

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

# Keys the Settings page is allowed to read/write in .env -- an explicit
# allowlist so a POST can't be used to inject arbitrary environment
# variables into the file. Numeric ones are validated as int-parseable.
SETTINGS_KEYS = {
    "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "ALLOWED_USERS", "WATCH_CHAT",
    "DOWNLOAD_DIR", "DOWNLOAD_DIR_MOVIES", "DOWNLOAD_DIR_TV",
    "SONARR_URL", "SONARR_API_KEY", "RADARR_URL", "RADARR_API_KEY",
    "SESSION_NAME", "MAX_CONCURRENT_DOWNLOADS", "PROGRESS_INTERVAL",
    "MAX_DOWNLOAD_RETRIES", "RETRY_BACKOFF_SECONDS", "ALLOWED_EXTENSIONS",
    "DB_PATH", "NOTIFY_INTERVAL_MINUTES", "RETENTION_DAYS",
    "WEB_ENABLED", "WEB_HOST", "WEB_PORT", "WEB_USERNAME", "WEB_PASSWORD",
    "LOG_LEVEL", "LOG_FILE", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT",
}

SETTINGS_NUMERIC_KEYS = {
    "TELEGRAM_API_ID", "MAX_CONCURRENT_DOWNLOADS", "PROGRESS_INTERVAL",
    "MAX_DOWNLOAD_RETRIES", "RETRY_BACKOFF_SECONDS", "WEB_PORT",
    "NOTIFY_INTERVAL_MINUTES", "RETENTION_DAYS", "LOG_MAX_BYTES",
    "LOG_BACKUP_COUNT",
}


def _disk_stats(config: Config) -> list[dict]:
    # Group configured download dirs by physical path so movies/TV sharing
    # a drive (or a single-drive setup) show one entry, not duplicates.
    roles_by_path: dict[str, list[str]] = {}

    if config.download_dir_movies:
        roles_by_path.setdefault(config.download_dir_movies, []).append("movies")
    if config.download_dir_tv:
        roles_by_path.setdefault(config.download_dir_tv, []).append("tv")
    if not config.download_dir_movies or not config.download_dir_tv:
        roles_by_path.setdefault(config.download_dir, []).append("default")

    disks = []
    for path, roles in roles_by_path.items():
        entry = {"path": path, "roles": roles}
        try:
            usage = shutil.disk_usage(path)
            entry["total"] = usage.total
            entry["free"] = usage.free
            entry["used_percent"] = (
                round((usage.used / usage.total) * 100, 1) if usage.total else 0
            )
        except OSError as e:
            entry["error"] = str(e)
        disks.append(entry)

    return disks


def create_app(
    config: Config,
    database: Database,
    bus: EventBus,
    queue: DownloadQueue,
) -> FastAPI:
    app = FastAPI(title="TeleFin", docs_url=None, redoc_url=None)
    security = HTTPBasic(auto_error=False)

    def check_auth(
        credentials: HTTPBasicCredentials | None = Depends(security),
    ) -> None:
        # No-op when no web credentials are configured (LAN-only use).
        if not config.web_username or not config.web_password:
            return

        valid = (
            credentials is not None
            and secrets.compare_digest(credentials.username, config.web_username)
            and secrets.compare_digest(credentials.password, config.web_password)
        )

        if not valid:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )

    def ws_authorized(websocket: WebSocket) -> bool:
        # Browsers reuse the page's HTTP Basic credentials on the WebSocket
        # handshake, so checking the Authorization header keeps the dashboard
        # JS free of any token plumbing. No query-param fallback: a password
        # in the URL ends up in browser history, proxy logs, and referrers.
        header = websocket.headers.get("authorization", "")

        if not header.lower().startswith("basic "):
            return False

        try:
            decoded = base64.b64decode(header[6:]).decode()
        except Exception:
            return False

        username, _, password = decoded.partition(":")
        return (
            secrets.compare_digest(username, config.web_username)
            and secrets.compare_digest(password, config.web_password)
        )

    # pages
    @app.get("/")
    async def index(_: None = Depends(check_auth)) -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    # REST API
    @app.get("/api/downloads")
    async def list_downloads(
        _: None = Depends(check_auth),
        filter: str = Query("all"),
        limit: int = Query(100, le=500),
    ) -> list[dict]:
        if filter == "active":
            return await database.list_downloads(active=True, limit=limit)
        if filter in ("all", ""):
            return await database.list_downloads(limit=limit)
        return await database.list_downloads(status=filter, limit=limit)

    @app.get("/api/stats")
    async def stats(_: None = Depends(check_auth)) -> dict:
        result = await database.get_stats()
        result["disks"] = _disk_stats(config)
        return result

    @app.get("/api/config")
    async def get_config(_: None = Depends(check_auth)) -> dict:
        return {
            "download_dir": config.download_dir,
            "watch_chat": ",".join(str(c) for c in config.watch_chats),
            "max_concurrent_downloads": config.max_concurrent_downloads,
            "allowed_extensions": sorted(config.allowed_extensions),
            "sonarr_configured": bool(config.sonarr_url and config.sonarr_api_key),
            "radarr_configured": bool(config.radarr_url and config.radarr_api_key),
        }

    @app.get("/api/settings")
    async def get_settings(_: None = Depends(check_auth)) -> dict:
        values = dotenv.dotenv_values(ENV_PATH)
        return {key: values.get(key, "") for key in SETTINGS_KEYS}

    @app.post("/api/settings")
    async def update_settings(
        payload: dict = Body(...),
        _: None = Depends(check_auth),
    ) -> dict:
        unknown = set(payload) - SETTINGS_KEYS

        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown setting(s): {', '.join(sorted(unknown))}",
            )

        for key in SETTINGS_NUMERIC_KEYS & set(payload):
            value = str(payload[key]).strip()

            if value and not re.fullmatch(r"-?\d+", value):
                raise HTTPException(
                    status_code=400,
                    detail=f"{key} must be a number, got: {value!r}",
                )

        for key, value in payload.items():
            dotenv.set_key(ENV_PATH, key, str(value))

        logger.info(
            "Settings updated via dashboard: %s (restart required to apply)",
            ", ".join(sorted(payload)),
        )

        return {"ok": True, "restart_required": True}

    @app.post("/api/downloads/{download_id}/retry")
    async def retry(
        download_id: int,
        _: None = Depends(check_auth),
    ) -> dict:
        record = await database.get_download(download_id)

        if not record:
            raise HTTPException(status_code=404, detail="Not found")

        if record["status"] == db.STATUS_DOWNLOADING:
            raise HTTPException(status_code=409, detail="Already downloading")

        await database.update_download(
            download_id,
            status=db.STATUS_QUEUED,
            error=None,
            downloaded=0,
            arr_result=None,
            started_at=None,
            completed_at=None,
        )
        await queue.enqueue(Job(download_id, None))

        return {"ok": True}

    @app.post("/api/downloads/{download_id}/cancel")
    async def cancel(
        download_id: int,
        _: None = Depends(check_auth),
    ) -> dict:
        record = await database.get_download(download_id)

        if not record:
            raise HTTPException(status_code=404, detail="Not found")

        if record["status"] == db.STATUS_QUEUED:
            cancelled = await queue.cancel_queued(download_id)
            if not cancelled:
                raise HTTPException(status_code=409, detail="No longer queued")
        elif record["status"] == db.STATUS_DOWNLOADING:
            queue.cancel(download_id)
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel a {record['status']} download",
            )

        return {"ok": True}

    @app.post("/api/downloads/{download_id}/notify")
    async def notify(
        download_id: int,
        _: None = Depends(check_auth),
    ) -> dict:
        try:
            arr_result = await queue.renotify(download_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

        return {"ok": True, "result": arr_result}

    @app.delete("/api/downloads/{download_id}")
    async def delete(
        download_id: int,
        _: None = Depends(check_auth),
        delete_file: bool = Query(False),
    ) -> dict:
        record = await database.delete_download(download_id)

        if not record:
            raise HTTPException(status_code=404, detail="Not found")

        if record["status"] == db.STATUS_DOWNLOADING:
            # Deleting the DB row alone leaves the worker downloading the
            # file in the background, tying up the queue. Signal it to
            # abort on its next progress tick (it cleans up its own .part
            # file when it does).
            queue.cancel(download_id)

        if delete_file and record.get("dest_path"):
            _remove_file(record["dest_path"])

        return {"ok": True}

    # live updates
    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if config.web_username and config.web_password:
            if not ws_authorized(websocket):
                await websocket.close(code=1008)
                return

        await websocket.accept()
        subscriber = bus.subscribe()

        try:
            while True:
                event = await subscriber.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            bus.unsubscribe(subscriber)

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app


def _remove_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning("Could not remove file %s: %s", path, e)

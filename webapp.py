import asyncio
import base64
import logging
import os
import re
import shutil
from pathlib import Path

import dotenv
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import db
from config import ENV_PATH, Config
from db import Database
from events import EventBus
from utils import updater
from utils.auth import (
    SESSION_COOKIE,
    SESSION_SECONDS,
    LoginLimiter,
    credentials_match,
    make_token,
    session_secret,
    verify_token,
)
from utils.schedule import parse_hhmm
from version import get_version
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
    "UPDATE_CHECK", "DOWNLOAD_WINDOW_START", "DOWNLOAD_WINDOW_END", "MAX_DOWNLOAD_SPEED_KBPS",
    "LOG_LEVEL", "LOG_FILE", "LOG_MAX_BYTES", "LOG_BACKUP_COUNT",
}

SETTINGS_NUMERIC_KEYS = {
    "TELEGRAM_API_ID", "MAX_CONCURRENT_DOWNLOADS", "PROGRESS_INTERVAL",
    "MAX_DOWNLOAD_RETRIES", "RETRY_BACKOFF_SECONDS", "WEB_PORT",
    "NOTIFY_INTERVAL_MINUTES", "RETENTION_DAYS", "MAX_DOWNLOAD_SPEED_KBPS",
    "LOG_MAX_BYTES",
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
    limiter = LoginLimiter()
    auth_enabled = bool(config.web_username and config.web_password)
    secret = (
        session_secret(config.web_username, config.web_password)
        if auth_enabled else b""
    )

    def basic_credentials(headers) -> tuple[str, str] | None:
        # HTTP Basic stays supported for scripts and API clients; the
        # dashboard itself signs in through the login page and a cookie.
        header = headers.get("authorization", "")

        if not header.lower().startswith("basic "):
            return None

        try:
            decoded = base64.b64decode(header[6:]).decode()
        except Exception:
            return None

        username, _, password = decoded.partition(":")
        return username, password

    def has_session(cookies) -> bool:
        return verify_token(secret, cookies.get(SESSION_COOKIE))

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def is_authenticated(request: Request) -> bool:
        if not auth_enabled:
            return True

        if has_session(request.cookies):
            return True

        creds = basic_credentials(request.headers)
        return bool(creds) and credentials_match(
            *creds, config.web_username, config.web_password
        )

    def check_auth(request: Request) -> None:
        # No-op when no web credentials are configured (LAN-only use).
        if not auth_enabled or has_session(request.cookies):
            return

        creds = basic_credentials(request.headers)

        if creds:
            # Wrong Basic credentials count toward the same lockout as the
            # login form, so the API can't be used to bypass it.
            key = client_key(request)
            wait = limiter.retry_after(key)

            if wait:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed attempts",
                    headers={"Retry-After": str(wait)},
                )

            if credentials_match(
                *creds, config.web_username, config.web_password
            ):
                limiter.reset(key)
                return

            limiter.record_failure(key)

        # No WWW-Authenticate header: that would make browsers pop up their
        # own sign-in box instead of letting the dashboard redirect to /login.
        raise HTTPException(status_code=401, detail="Unauthorized")

    def ws_authorized(websocket: WebSocket) -> bool:
        # Browsers send the session cookie on the same-origin WebSocket
        # handshake. No query-param fallback: a password in the URL ends up
        # in browser history, proxy logs, and referrers.
        if has_session(websocket.cookies):
            return True

        creds = basic_credentials(websocket.headers)
        return bool(creds) and credentials_match(
            *creds, config.web_username, config.web_password
        )

    @app.middleware("http")
    async def revalidate_static_files(request, call_next):
        # StaticFiles sends ETag/Last-Modified but no Cache-Control, so
        # browsers cache app.js heuristically and keep running the old
        # script after an update. no-cache makes them revalidate each time
        # (a cheap 304 when nothing changed).
        response = await call_next(request)

        if request.url.path.startswith("/static/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache"

        return response

    # pages
    @app.get("/")
    async def index(request: Request):
        if not is_authenticated(request):
            return RedirectResponse("/login", status_code=302)

        return FileResponse(WEB_DIR / "index.html")

    @app.get("/login")
    async def login_page(request: Request):
        if is_authenticated(request):
            return RedirectResponse("/", status_code=302)

        return FileResponse(WEB_DIR / "login.html")

    @app.post("/api/login")
    async def login(request: Request, payload: dict = Body(...)) -> JSONResponse:
        if not auth_enabled:
            return JSONResponse({"ok": True})

        key = client_key(request)
        wait = limiter.retry_after(key)

        if wait:
            return JSONResponse(
                {"detail": "Too many failed attempts"},
                status_code=429,
                headers={"Retry-After": str(wait)},
            )

        if not credentials_match(
            str(payload.get("username", "")),
            str(payload.get("password", "")),
            config.web_username,
            config.web_password,
        ):
            limiter.record_failure(key)
            logger.warning("Failed dashboard login from %s", key)
            return JSONResponse({"detail": "Invalid username or password"}, status_code=401)

        limiter.reset(key)
        response = JSONResponse({"ok": True})
        response.set_cookie(
            SESSION_COOKIE,
            make_token(secret),
            max_age=SESSION_SECONDS,
            httponly=True,
            samesite="lax",
            secure=(
                request.url.scheme == "https"
                or request.headers.get("x-forwarded-proto") == "https"
            ),
        )
        return response

    @app.post("/api/logout")
    async def logout() -> JSONResponse:
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE)
        return response

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
            "auth_enabled": bool(config.web_username and config.web_password),
            "version": get_version(),
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

        for key in ("DOWNLOAD_WINDOW_START", "DOWNLOAD_WINDOW_END"):
            value = str(payload.get(key, "")).strip()

            if value and parse_hhmm(value) is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"{key} must be a time like 23:30, got: {value!r}",
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

    @app.get("/api/updates")
    async def get_updates(
        _: None = Depends(check_auth),
        refresh: bool = Query(False),
    ) -> dict:
        if not config.update_check:
            return {
                "current": get_version(), "current_known": True,
                "method": updater.install_method(),
                "check_ok": False, "latest": None, "update_available": False,
                "releases": [], "check_disabled": True,
                "can_install": False,
            }

        status = await updater.get_status(force=refresh)
        status["check_disabled"] = False
        # Installing runs git/pip on the host and restarts the process, so
        # it is only offered when the dashboard is behind a login.
        status["can_install"] = (
            status["method"] == "git"
            and bool(config.web_username and config.web_password)
        )
        return status

    @app.post("/api/updates/install")
    async def install_update(
        _: None = Depends(check_auth),
        payload: dict = Body(...),
    ) -> dict:
        if not (config.web_username and config.web_password):
            raise HTTPException(
                status_code=403,
                detail="Set WEB_USERNAME and WEB_PASSWORD before installing "
                       "updates from the dashboard",
            )

        status = await updater.get_status()
        version = str(payload.get("version", ""))

        if status["method"] != "git":
            raise HTTPException(
                status_code=409, detail="This install can't update itself"
            )

        if version not in {r["version"] for r in status["releases"]}:
            raise HTTPException(status_code=400, detail="Unknown release")

        if await database.list_downloads(active=True, limit=1):
            raise HTTPException(
                status_code=409,
                detail="Finish or cancel active downloads before updating "
                       "(a restart would interrupt them)",
            )

        try:
            await updater.install(version)
        except updater.UpdateError as e:
            raise HTTPException(status_code=500, detail=str(e))

        asyncio.get_running_loop().call_later(1.0, updater.restart)
        return {"ok": True, "restarting": True, "version": version}

    @app.get("/api/queue")
    async def queue_state(_: None = Depends(check_auth)) -> dict:
        return queue.state()

    @app.post("/api/queue/pause")
    async def pause_queue(_: None = Depends(check_auth)) -> dict:
        queue.pause()
        return queue.state()

    @app.post("/api/queue/resume")
    async def resume_queue(_: None = Depends(check_auth)) -> dict:
        queue.resume()
        return queue.state()

    @app.post("/api/downloads/{download_id}/prioritize")
    async def prioritize(
        download_id: int,
        _: None = Depends(check_auth),
    ) -> dict:
        record = await database.get_download(download_id)

        if not record:
            raise HTTPException(status_code=404, detail="Not found")

        if not await queue.promote(download_id):
            raise HTTPException(status_code=409, detail="No longer queued")

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

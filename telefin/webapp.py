import asyncio
import base64
import logging
import os
import secrets
from pathlib import Path

from fastapi import (
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
from config import Config
from db import Database
from events import EventBus
from worker import DownloadQueue, Job

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

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
        # JS free of any token plumbing.
        header = websocket.headers.get("authorization", "")

        if header.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode()
            except Exception:
                return False
            username, _, password = decoded.partition(":")
            return (
                secrets.compare_digest(username, config.web_username)
                and secrets.compare_digest(password, config.web_password)
            )

        # Fallback for non-browser clients: /ws?token=<WEB_PASSWORD>.
        token = websocket.query_params.get("token", "")
        return secrets.compare_digest(token, config.web_password)

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
        return await database.get_stats()

    @app.get("/api/config")
    async def get_config(_: None = Depends(check_auth)) -> dict:
        return {
            "download_dir": config.download_dir,
            "watch_chat": config.watch_chat,
            "max_concurrent_downloads": config.max_concurrent_downloads,
            "allowed_extensions": sorted(config.allowed_extensions),
            "sonarr_configured": bool(config.sonarr_url and config.sonarr_api_key),
            "radarr_configured": bool(config.radarr_url and config.radarr_api_key),
        }

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

    @app.delete("/api/downloads/{download_id}")
    async def delete(
        download_id: int,
        _: None = Depends(check_auth),
        delete_file: bool = Query(False),
    ) -> dict:
        record = await database.delete_download(download_id)

        if not record:
            raise HTTPException(status_code=404, detail="Not found")

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

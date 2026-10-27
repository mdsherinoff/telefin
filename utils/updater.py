import asyncio
import logging
import os
import re
import sys
import time

import httpx

from version import APP_DIR, get_version, is_docker

logger = logging.getLogger(__name__)

REPO = "mdsherinoff/telefin"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases"
CACHE_SECONDS = 3600
TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+")

_cache: dict = {"at": 0.0, "releases": None}


class UpdateError(Exception):
    pass


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    # "v0.5.0" and "v0.5.0-3-gabc123" (git describe, 3 commits past the
    # tag) both parse to (0, 5, 0); anything else (e.g. "dev") is None.
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (raw or "").strip())

    return tuple(int(g) for g in match.groups()) if match else None


def install_method() -> str:
    # "docker": replace the container/image; "git": we can check out a tag
    # in place; "manual": unknown layout, show instructions only.
    if is_docker():
        return "docker"

    if (APP_DIR / ".git").exists():
        return "git"

    return "manual"


async def fetch_releases(force: bool = False) -> list[dict] | None:
    # Published (non-draft, non-prerelease) releases, newest first, or None
    # when GitHub can't be reached. Cached so the dashboard polling can't
    # exhaust GitHub's unauthenticated rate limit.
    if (
        not force
        and _cache["releases"] is not None
        and time.monotonic() - _cache["at"] < CACHE_SECONDS
    ):
        return _cache["releases"]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                RELEASES_URL,
                params={"per_page": 15},
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            raw = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Could not check for updates: %s", e)
        return _cache["releases"]

    releases = [
        {
            "version": r["tag_name"],
            "name": r.get("name") or r["tag_name"],
            "date": r.get("published_at"),
            "body": r.get("body") or "",
            "url": r.get("html_url"),
        }
        for r in raw
        if not r.get("draft")
        and not r.get("prerelease")
        and parse_version(r.get("tag_name")) is not None
    ]
    releases.sort(key=lambda r: parse_version(r["version"]), reverse=True)

    _cache.update(at=time.monotonic(), releases=releases)
    return releases


def build_status(current: str, releases: list[dict] | None) -> dict:
    current_v = parse_version(current)
    latest = releases[0] if releases else None
    update_available = bool(
        latest
        and current_v is not None
        and parse_version(latest["version"]) > current_v
    )

    return {
        "current": current,
        "current_known": current_v is not None,
        "method": install_method(),
        "check_ok": releases is not None,
        "latest": latest["version"] if latest else None,
        "update_available": update_available,
        "releases": releases or [],
    }


async def get_status(force: bool = False) -> dict:
    return build_status(get_version(), await fetch_releases(force))


async def _run(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *args, cwd=APP_DIR,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text = output.decode(errors="replace").strip()

    if process.returncode != 0:
        raise UpdateError(f"`{' '.join(args)}` failed: {text[-500:]}")

    return text


async def install(tag: str) -> None:
    # Checks out a release tag in place and installs its dependencies,
    # rolling back to the previous commit if anything fails. The caller
    # restarts the process afterwards.
    if install_method() != "git":
        raise UpdateError("This install can't update itself")

    if not TAG_PATTERN.fullmatch(tag):
        raise UpdateError(f"Invalid version: {tag!r}")

    if await _run("git", "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError(
            "The install directory has local changes; commit or discard "
            "them first"
        )

    previous = await _run("git", "rev-parse", "HEAD")

    try:
        await _run("git", "fetch", "--tags", "--force", "origin")
        await _run("git", "checkout", "--quiet", f"refs/tags/{tag}")
        await _run(
            sys.executable, "-m", "pip", "install", "--quiet",
            "-r", "requirements.txt",
        )
    except UpdateError:
        logger.exception("Update to %s failed, rolling back", tag)

        try:
            await _run("git", "checkout", "--quiet", previous)
        except UpdateError:
            logger.exception("Rollback to %s failed", previous)

        raise

    logger.info("Updated to %s", tag)


def restart() -> None:
    # Replace this process with a fresh interpreter running the new code.
    # Descriptors are close-on-exec, so the web port and Telegram session
    # are released for the new process.
    logger.info("Restarting TeleFin")
    os.execv(sys.executable, [sys.executable, *sys.argv])

import logging
import httpx

logger = logging.getLogger(__name__)


async def trigger_radarr_scan(path: str, radarr_url: str | None, radarr_api_key: str | None) -> bool:
    # Trigger Radarr DownloadedMoviesScan for a freshly downloaded file.
    if not radarr_url or not radarr_api_key:
        logger.error("Radarr environment variables missing")
        return False

    url = f"{radarr_url.rstrip('/')}/api/v3/command"

    headers = {"X-Api-Key": radarr_api_key}
    payload = {"name": "DownloadedMoviesScan", "path": path}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        logger.info("Radarr scan triggered successfully for: %s", path)
        return True

    except httpx.HTTPError as e:
        logger.error("Failed to trigger Radarr scan: %s", e)
        return False

import logging
import httpx

logger = logging.getLogger(__name__)


async def trigger_sonarr_scan(path: str, sonarr_url: str | None, sonarr_api_key: str | None) -> bool:
    # Trigger Sonarr DownloadedEpisodesScan for a freshly downloaded file.
    if not sonarr_url or not sonarr_api_key:
        logger.error("Sonarr environment variables missing")
        return False

    url = f"{sonarr_url.rstrip('/')}/api/v3/command"

    headers = {"X-Api-Key": sonarr_api_key}
    payload = {"name": "DownloadedEpisodesScan", "path": path}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        logger.info("Sonarr scan triggered successfully for: %s", path)
        return True

    except httpx.HTTPError as e:
        logger.error("Failed to trigger Sonarr scan: %s", e)
        return False

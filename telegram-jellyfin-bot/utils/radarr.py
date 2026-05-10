import os
import logging
import requests

logger = logging.getLogger(__name__)


def trigger_radarr_scan(path: str) -> bool:
    """
    Trigger Radarr DownloadedMoviesScan
    """

    radarr_url = os.getenv("RADARR_URL")
    radarr_api_key = os.getenv("RADARR_API_KEY")

    if not radarr_url or not radarr_api_key:
        logger.error("Radarr environment variables missing")
        return False

    url = f"{radarr_url}/api/v3/command"

    headers = {
        "X-Api-Key": radarr_api_key
    }

    payload = {
        "name": "DownloadedMoviesScan",
        "path": path
    }

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        logger.info(f"Radarr scan triggered successfully for: {path}")

        return True

    except requests.RequestException as e:

        logger.error(f"Failed to trigger Radarr scan: {e}")

        return False
import os
import logging
import requests

logger = logging.getLogger(__name__)


def trigger_sonarr_scan(path: str) -> bool:
    """
    Trigger Sonarr DownloadedEpisodesScan
    """

    sonarr_url = os.getenv("SONARR_URL")
    sonarr_api_key = os.getenv("SONARR_API_KEY")

    if not sonarr_url or not sonarr_api_key:
        logger.error("Sonarr environment variables missing")
        return False

    url = f"{sonarr_url}/api/v3/command"

    headers = {
        "X-Api-Key": sonarr_api_key
    }

    payload = {
        "name": "DownloadedEpisodesScan",
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

        logger.info(f"Sonarr scan triggered successfully for: {path}")

        return True

    except requests.RequestException as e:

        logger.error(f"Failed to trigger Sonarr scan: {e}")

        return False
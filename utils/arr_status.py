import logging

import httpx

logger = logging.getLogger(__name__)

# Sonarr/Radarr history eventType for "imported from a download folder",
# which is what a DownloadedEpisodesScan / DownloadedMoviesScan produces.
EVENT_DOWNLOAD_FOLDER_IMPORTED = 3


async def fetch_imported_paths(url: str | None, api_key: str | None) -> set[str] | None:
    # Source paths Sonarr/Radarr report having imported recently, or None
    # when the app isn't configured/reachable (callers must not treat that
    # as "nothing imported").
    if not url or not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{url.rstrip('/')}/api/v3/history",
                headers={"X-Api-Key": api_key},
                params={
                    "page": 1,
                    "pageSize": 200,
                    "sortKey": "date",
                    "sortDirection": "descending",
                    "eventType": EVENT_DOWNLOAD_FOLDER_IMPORTED,
                },
            )
            response.raise_for_status()
            records = response.json().get("records", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Could not read import history from %s: %s", url, e)
        return None

    return {
        r["data"]["droppedPath"]
        for r in records
        if isinstance(r.get("data"), dict) and r["data"].get("droppedPath")
    }

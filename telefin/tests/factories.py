from config import DEFAULT_EXTENSIONS, Config


def make_config(**overrides) -> Config:
    defaults = dict(
        api_id=1, api_hash="hash", session_name="session",
        watch_chats=["me"], allowed_users=[1],
        download_dir="/srv/media/incoming",
        download_dir_movies=None, download_dir_tv=None,
        db_path="telefin.db",
        allowed_extensions=set(DEFAULT_EXTENSIONS),
        max_concurrent_downloads=1, progress_interval=5,
        max_download_retries=3, retry_backoff_seconds=10,
        sonarr_url=None, sonarr_api_key=None,
        radarr_url=None, radarr_api_key=None,
        web_enabled=True, web_host="0.0.0.0", web_port=8420,
        web_username=None, web_password=None,
    )
    defaults.update(overrides)
    return Config(**defaults)

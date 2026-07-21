from fastapi.testclient import TestClient

import webapp
from events import EventBus
from tests.factories import make_config
from webapp import _disk_stats, create_app


class TestDiskStats:
    def test_single_default_dir(self, tmp_path):
        config = make_config(download_dir=str(tmp_path))

        disks = _disk_stats(config)

        assert len(disks) == 1
        assert disks[0]["path"] == str(tmp_path)
        assert disks[0]["roles"] == ["default"]
        assert "free" in disks[0]
        assert "total" in disks[0]

    def test_split_movies_and_tv_dirs(self, tmp_path):
        movies = tmp_path / "movies"
        tv = tmp_path / "tv"
        movies.mkdir()
        tv.mkdir()
        config = make_config(
            download_dir=str(tmp_path),
            download_dir_movies=str(movies),
            download_dir_tv=str(tv),
        )

        disks = _disk_stats(config)

        paths = {d["path"]: d["roles"] for d in disks}
        assert paths == {str(movies): ["movies"], str(tv): ["tv"]}

    def test_partial_split_keeps_default_for_unset_type(self, tmp_path):
        movies = tmp_path / "movies"
        movies.mkdir()
        config = make_config(
            download_dir=str(tmp_path),
            download_dir_movies=str(movies),
            download_dir_tv=None,
        )

        disks = _disk_stats(config)

        paths = {d["path"]: d["roles"] for d in disks}
        assert paths == {str(movies): ["movies"], str(tmp_path): ["default"]}

    def test_unreachable_path_reports_error(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        config = make_config(download_dir=str(missing))

        disks = _disk_stats(config)

        assert len(disks) == 1
        assert "error" in disks[0]


def make_client(tmp_path, monkeypatch) -> TestClient:
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_API_ID=1\nRADARR_API_KEY=oldkey\n")
    monkeypatch.setattr(webapp, "ENV_PATH", env_path)

    config = make_config()
    app = create_app(config, database=None, bus=EventBus(), queue=None)
    return TestClient(app), env_path


class TestSettingsEndpoint:
    def test_get_returns_known_keys_from_env_file(self, tmp_path, monkeypatch):
        client, _ = make_client(tmp_path, monkeypatch)

        res = client.get("/api/settings")

        assert res.status_code == 200
        body = res.json()
        assert body["TELEGRAM_API_ID"] == "1"
        assert body["RADARR_API_KEY"] == "oldkey"
        assert body["SONARR_API_KEY"] == ""  # not set in the file -> empty string

    def test_post_writes_to_env_file(self, tmp_path, monkeypatch):
        client, env_path = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"RADARR_API_KEY": "newkey"})

        assert res.status_code == 200
        assert res.json() == {"ok": True, "restart_required": True}
        assert "RADARR_API_KEY='newkey'" in env_path.read_text()

    def test_post_rejects_unknown_key(self, tmp_path, monkeypatch):
        client, _ = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"NOT_A_REAL_SETTING": "x"})

        assert res.status_code == 400

    def test_post_rejects_non_numeric_value_for_numeric_key(self, tmp_path, monkeypatch):
        client, _ = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"WEB_PORT": "not-a-number"})

        assert res.status_code == 400

    def test_post_accepts_numeric_value_for_numeric_key(self, tmp_path, monkeypatch):
        client, env_path = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"WEB_PORT": "9000"})

        assert res.status_code == 200
        assert "WEB_PORT='9000'" in env_path.read_text()

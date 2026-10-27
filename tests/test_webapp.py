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


class FakeQueue:
    def __init__(self):
        self.paused = False

    def state(self):
        return {"paused": self.paused, "in_window": True}

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class TestQueueEndpoints:
    def test_pause_and_resume(self):
        app = create_app(make_config(), database=None, bus=EventBus(), queue=FakeQueue())
        client = TestClient(app)

        assert client.post("/api/queue/pause").json()["paused"] is True
        assert client.get("/api/queue").json()["paused"] is True
        assert client.post("/api/queue/resume").json()["paused"] is False

    def test_requires_auth_when_configured(self):
        config = make_config(web_username="u", web_password="p")
        client = TestClient(create_app(config, None, EventBus(), FakeQueue()))

        assert client.post("/api/queue/pause").status_code == 401
        assert client.post("/api/queue/pause", auth=("u", "p")).status_code == 200


class TestWindowSettingValidation:
    def test_rejects_bad_time(self, tmp_path, monkeypatch):
        client, _ = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"DOWNLOAD_WINDOW_START": "7pm"})

        assert res.status_code == 400

    def test_accepts_good_time(self, tmp_path, monkeypatch):
        client, _ = make_client(tmp_path, monkeypatch)

        res = client.post("/api/settings", json={"DOWNLOAD_WINDOW_START": "01:00"})

        assert res.status_code == 200


class FakeDb:
    def __init__(self, active=False):
        self.active = active

    async def list_downloads(self, **_):
        return [{"id": 1}] if self.active else []


def _update_client(monkeypatch, *, auth=True, method="git", active=False, installs=None):
    from utils import updater

    status = {
        "current": "v0.5.0", "current_known": True, "method": method,
        "check_ok": True, "latest": "v0.6.0", "update_available": True,
        "releases": [{"version": "v0.6.0"}],
    }

    async def fake_status(force=False):
        return dict(status)

    async def fake_install(tag):
        if installs is not None:
            installs.append(tag)

    monkeypatch.setattr(updater, "get_status", fake_status)
    monkeypatch.setattr(updater, "install", fake_install)
    monkeypatch.setattr(updater, "restart", lambda: None)

    config = make_config(
        web_username="u" if auth else None, web_password="p" if auth else None
    )
    app = create_app(config, FakeDb(active), EventBus(), FakeQueue())
    return TestClient(app), ({"auth": ("u", "p")} if auth else {})


class TestUpdateEndpoints:
    def test_install_offered_only_with_login_on_git_install(self, monkeypatch):
        client, kw = _update_client(monkeypatch)
        assert client.get("/api/updates", **kw).json()["can_install"] is True

        client, kw = _update_client(monkeypatch, auth=False)
        assert client.get("/api/updates").json()["can_install"] is False

        client, kw = _update_client(monkeypatch, method="docker")
        assert client.get("/api/updates", **kw).json()["can_install"] is False

    def test_install_runs_and_restarts(self, monkeypatch):
        installs = []
        client, kw = _update_client(monkeypatch, installs=installs)

        res = client.post("/api/updates/install", json={"version": "v0.6.0"}, **kw)

        assert res.status_code == 200
        assert installs == ["v0.6.0"]

    def test_install_refused_without_login(self, monkeypatch):
        client, _ = _update_client(monkeypatch, auth=False)

        res = client.post("/api/updates/install", json={"version": "v0.6.0"})

        assert res.status_code == 403

    def test_install_refused_for_unknown_version(self, monkeypatch):
        client, kw = _update_client(monkeypatch)

        res = client.post("/api/updates/install", json={"version": "v9.9.9"}, **kw)

        assert res.status_code == 400

    def test_install_refused_while_downloading(self, monkeypatch):
        client, kw = _update_client(monkeypatch, active=True)

        res = client.post("/api/updates/install", json={"version": "v0.6.0"}, **kw)

        assert res.status_code == 409


class TestStaticCaching:
    def test_static_files_must_revalidate(self):
        client = TestClient(create_app(make_config(), None, EventBus(), None))

        for path in ("/", "/static/app.js"):
            assert client.get(path).headers["cache-control"] == "no-cache"

    def test_api_responses_are_untouched(self):
        client = TestClient(create_app(make_config(), None, EventBus(), None))

        assert "cache-control" not in client.get("/api/health").headers

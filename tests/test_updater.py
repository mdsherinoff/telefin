import asyncio

import pytest

from utils import updater
from utils.updater import build_status, parse_version

RELEASES = [
    {"version": "v0.6.0", "name": "v0.6.0", "date": None, "body": "", "url": None},
    {"version": "v0.5.0", "name": "v0.5.0", "date": None, "body": "", "url": None},
]


class TestParseVersion:
    def test_plain_tag(self):
        assert parse_version("v0.5.0") == (0, 5, 0)

    def test_git_describe_past_tag(self):
        assert parse_version("v0.5.0-3-gabc123") == (0, 5, 0)

    def test_unparseable(self):
        assert parse_version("dev") is None
        assert parse_version(None) is None

    def test_compares_numerically_not_lexically(self):
        assert parse_version("v0.10.0") > parse_version("v0.9.0")


class TestBuildStatus:
    def test_update_available(self):
        status = build_status("v0.5.0", RELEASES)
        assert status["update_available"] is True
        assert status["latest"] == "v0.6.0"

    def test_up_to_date(self):
        assert build_status("v0.6.0", RELEASES)["update_available"] is False

    def test_dev_build_is_not_comparable(self):
        status = build_status("dev", RELEASES)
        assert status["update_available"] is False
        assert status["current_known"] is False

    def test_github_unreachable(self):
        status = build_status("v0.5.0", None)
        assert status["check_ok"] is False
        assert status["update_available"] is False


class TestInstall:
    def test_rejects_non_git_install(self, monkeypatch):
        monkeypatch.setattr(updater, "install_method", lambda: "docker")
        with pytest.raises(updater.UpdateError):
            asyncio.run(updater.install("v0.6.0"))

    def test_rejects_malformed_tag(self, monkeypatch):
        monkeypatch.setattr(updater, "install_method", lambda: "git")
        with pytest.raises(updater.UpdateError):
            asyncio.run(updater.install("main; rm -rf /"))

    def test_rolls_back_when_pip_fails(self, monkeypatch):
        monkeypatch.setattr(updater, "install_method", lambda: "git")
        calls = []

        async def fake_run(*args):
            calls.append(args)
            if args[:2] == ("git", "status"):
                return ""
            if args[:2] == ("git", "rev-parse"):
                return "prevsha"
            if "pip" in args:
                raise updater.UpdateError("pip exploded")
            return ""

        monkeypatch.setattr(updater, "_run", fake_run)

        with pytest.raises(updater.UpdateError):
            asyncio.run(updater.install("v0.6.0"))

        assert calls[-1] == ("git", "checkout", "--quiet", "prevsha")

    def test_refuses_dirty_tree(self, monkeypatch):
        monkeypatch.setattr(updater, "install_method", lambda: "git")

        async def fake_run(*args):
            return " M worker.py" if args[:2] == ("git", "status") else ""

        monkeypatch.setattr(updater, "_run", fake_run)

        with pytest.raises(updater.UpdateError):
            asyncio.run(updater.install("v0.6.0"))

from config import DEFAULT_EXTENSIONS, _parse_chats, _parse_extensions, _parse_users
from tests.factories import make_config


class TestParseUsers:
    def test_single(self):
        assert _parse_users("123") == [123]

    def test_multiple(self):
        assert _parse_users("123, 456,789") == [123, 456, 789]

    def test_empty(self):
        assert _parse_users("") == []

    def test_ignores_non_numeric(self):
        assert _parse_users("123,abc,456") == [123, 456]


class TestParseChats:
    def test_default_is_me(self):
        assert _parse_chats("") == ["me"]

    def test_username(self):
        assert _parse_chats("me") == ["me"]

    def test_numeric_ids_become_int(self):
        assert _parse_chats("-1001234567890") == [-1001234567890]

    def test_mixed(self):
        assert _parse_chats("me,-1001234567890,@somegroup") == [
            "me", -1001234567890, "@somegroup",
        ]


class TestParseExtensions:
    def test_adds_leading_dot(self):
        assert _parse_extensions("mkv,mp4") == {".mkv", ".mp4"}

    def test_keeps_existing_dot(self):
        assert _parse_extensions(".mkv,.mp4") == {".mkv", ".mp4"}

    def test_lowercases(self):
        assert _parse_extensions("MKV") == {".mkv"}

    def test_empty_falls_back_to_defaults(self):
        assert _parse_extensions("") == set(DEFAULT_EXTENSIONS)


class TestDownloadDirFor:
    def test_falls_back_to_shared_dir_when_unset(self):
        config = make_config()
        assert config.download_dir_for("movie") == "/srv/media/incoming"
        assert config.download_dir_for("tv") == "/srv/media/incoming"

    def test_uses_movies_override(self):
        config = make_config(download_dir_movies="/media/Movies/incoming")
        assert config.download_dir_for("movie") == "/media/Movies/incoming"
        assert config.download_dir_for("tv") == "/srv/media/incoming"

    def test_uses_tv_override(self):
        config = make_config(download_dir_tv="/media/TVShows/incoming")
        assert config.download_dir_for("tv") == "/media/TVShows/incoming"
        assert config.download_dir_for("movie") == "/srv/media/incoming"

    def test_both_overrides_set(self):
        config = make_config(
            download_dir_movies="/media/Movies/incoming",
            download_dir_tv="/media/TVShows/incoming",
        )
        assert config.download_dir_for("movie") == "/media/Movies/incoming"
        assert config.download_dir_for("tv") == "/media/TVShows/incoming"


class TestAllDownloadDirs:
    def test_only_shared_dir(self):
        config = make_config()
        assert config.all_download_dirs() == ["/srv/media/incoming"]

    def test_includes_set_overrides(self):
        config = make_config(
            download_dir_movies="/media/Movies/incoming",
            download_dir_tv="/media/TVShows/incoming",
        )
        assert config.all_download_dirs() == [
            "/srv/media/incoming",
            "/media/Movies/incoming",
            "/media/TVShows/incoming",
        ]

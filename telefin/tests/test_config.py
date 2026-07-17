from config import DEFAULT_EXTENSIONS, _parse_chats, _parse_extensions, _parse_users


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

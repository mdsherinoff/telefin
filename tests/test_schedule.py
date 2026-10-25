from datetime import time

from utils.schedule import in_window, parse_hhmm


class TestParse:
    def test_valid(self):
        assert parse_hhmm("07:30") == time(7, 30)

    def test_invalid_or_blank(self):
        assert parse_hhmm("7pm") is None
        assert parse_hhmm("") is None
        assert parse_hhmm(None) is None


class TestInWindow:
    def test_no_window_always_allowed(self):
        assert in_window(time(3, 0), None, None)

    def test_same_day_window(self):
        assert in_window(time(2, 0), "01:00", "07:00")
        assert not in_window(time(7, 0), "01:00", "07:00")  # end exclusive
        assert not in_window(time(12, 0), "01:00", "07:00")

    def test_overnight_window(self):
        assert in_window(time(23, 0), "22:00", "06:00")
        assert in_window(time(5, 59), "22:00", "06:00")
        assert not in_window(time(12, 0), "22:00", "06:00")

from utils.telegram_helpers import (
    format_size,
    is_allowed_user,
    is_tv_show,
    make_progress_bar,
    safe_destination,
    sanitize_filename,
)


class TestSanitizeFilename:
    def test_keeps_safe_characters(self):
        assert sanitize_filename("Show.Name (2020) [1080p].mkv") == (
            "Show.Name (2020) [1080p].mkv"
        )

    def test_strips_path_and_control_characters(self):
        assert sanitize_filename("../../etc/passwd") == "....etcpasswd"
        assert sanitize_filename("a/b\\c") == "abc"

    def test_falls_back_when_nothing_left(self):
        assert sanitize_filename("???///") == "unknown_file"

    def test_strips_surrounding_whitespace(self):
        assert sanitize_filename("  movie.mkv  ") == "movie.mkv"


class TestIsAllowedUser:
    def test_allowed(self):
        assert is_allowed_user(123, [123, 456]) is True

    def test_not_allowed(self):
        assert is_allowed_user(789, [123, 456]) is False

    def test_empty_allowlist(self):
        assert is_allowed_user(123, []) is False


class TestIsTvShow:
    def test_sxxexx_pattern(self):
        assert is_tv_show("Show.Name.S01E02.mkv") is True

    def test_nxn_pattern(self):
        assert is_tv_show("Show.Name.1x02.mkv") is True

    def test_movie_is_not_tv(self):
        assert is_tv_show("Some.Movie.2020.mkv") is False

    def test_case_insensitive(self):
        assert is_tv_show("show.name.s01e02.MKV") is True


class TestSafeDestination:
    def test_basic_join(self, tmp_path):
        safe_name, dest_path = safe_destination(str(tmp_path), "movie.mkv")
        assert safe_name == "movie.mkv"
        assert dest_path == str(tmp_path / "movie.mkv")

    def test_strips_directory_components(self, tmp_path):
        safe_name, dest_path = safe_destination(str(tmp_path), "../../movie.mkv")
        assert "/" not in safe_name
        assert dest_path == str(tmp_path / safe_name)

    def test_uniquifies_on_collision(self, tmp_path):
        (tmp_path / "movie.mkv").write_bytes(b"existing")

        safe_name, dest_path = safe_destination(str(tmp_path), "movie.mkv")

        assert safe_name == "movie (1).mkv"
        assert dest_path == str(tmp_path / "movie (1).mkv")

    def test_uniquifies_past_multiple_collisions(self, tmp_path):
        (tmp_path / "movie.mkv").write_bytes(b"a")
        (tmp_path / "movie (1).mkv").write_bytes(b"b")

        safe_name, _ = safe_destination(str(tmp_path), "movie.mkv")

        assert safe_name == "movie (2).mkv"


class TestFormatSize:
    def test_zero(self):
        assert format_size(0) == "0B"

    def test_bytes(self):
        assert format_size(500) == "500.00 B"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.00 MB"


class TestMakeProgressBar:
    def test_empty(self):
        bar = make_progress_bar(0.0, width=10)
        assert bar == "[" + "░" * 10 + "]"

    def test_full(self):
        bar = make_progress_bar(1.0, width=10)
        assert bar == "[" + "█" * 10 + "]"

    def test_clamps_out_of_range(self):
        assert make_progress_bar(-1.0, width=4) == "[░░░░]"
        assert make_progress_bar(2.0, width=4) == "[████]"

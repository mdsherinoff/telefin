from tests.factories import make_config
from webapp import _disk_stats


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

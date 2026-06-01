import dump


class TestCleanAlbumTitle:
    def test_replaces_illegal_characters(self):
        title = r'a\b/c:d*e?f"g<h>i|j'
        assert dump._clean_album_title(title) == "a_b_c_d_e_f_g_h_i_j"

    def test_strips_trailing_dots_and_spaces(self):
        assert dump._clean_album_title("  My Album . ") == "My Album"

    def test_empty_after_cleaning_returns_default(self):
        assert dump._clean_album_title("...") == "temp"

    def test_respects_custom_default(self):
        assert dump._clean_album_title("", default_title="fallback") == "fallback"

    def test_keeps_normal_title(self):
        assert dump._clean_album_title("Holiday Photos 2024") == "Holiday Photos 2024"


class TestTruncate:
    def test_returns_unchanged_when_short(self):
        assert dump._truncate("short.jpg") == "short.jpg"

    def test_truncates_long_text_keeping_tail(self):
        text = "a" * 60
        result = dump._truncate(text, length=10)
        assert len(result) == 10
        assert result.startswith("…")
        assert result.endswith("a" * 9)

    def test_exact_length_unchanged(self):
        text = "x" * 48
        assert dump._truncate(text) == text


class TestReadUrlsFromFile:
    def test_reads_one_url_per_line(self, tmp_path):
        f = tmp_path / "albums.txt"
        f.write_text(
            "https://www.erome.com/a/aaaa\nhttps://www.erome.com/a/bbbb\n",
            encoding="utf-8",
        )
        assert dump._read_urls_from_file(str(f)) == [
            "https://www.erome.com/a/aaaa",
            "https://www.erome.com/a/bbbb",
        ]

    def test_skips_blank_lines_and_comments(self, tmp_path):
        f = tmp_path / "albums.txt"
        f.write_text(
            "# Favorites\n"
            "https://www.erome.com/a/aaaa\n"
            "\n"
            "  \n"
            "# another comment\n"
            "https://www.erome.com/a/bbbb\n",
            encoding="utf-8",
        )
        assert dump._read_urls_from_file(str(f)) == [
            "https://www.erome.com/a/aaaa",
            "https://www.erome.com/a/bbbb",
        ]

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert dump._read_urls_from_file(str(f)) == []


class TestGetFinalDownloadPath:
    def test_creates_directory_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = dump._get_final_download_path("My Album")
        assert path == dump.Path("downloads") / "My Album"
        assert path.exists()
        assert path.is_dir()

    def test_returns_existing_path_without_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        first = dump._get_final_download_path("My Album")
        second = dump._get_final_download_path("My Album")
        assert first == second
        assert second.exists()

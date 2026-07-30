import os
from datetime import datetime

import pytest

from weekly_report.report_file_manager import (
    ReportFileManager,
    blank_report_content,
    import_report,
    is_blank_report_text,
    parse_created_marker,
    report_date,
    strip_report_marks,
)


def write_history(home, *dates: datetime, content: str = "old report"):
    home.ensure()
    paths = []
    for date in dates:
        path = home.history_dir / f"report-{date.strftime('%Y%m%d-%H%M%S')}.md"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


class TestReportDate:
    def test_parses_report_filenames(self):
        assert report_date("report-20260730-091331.md") == datetime(2026, 7, 30, 9, 13, 31)

    @pytest.mark.parametrize(
        "name",
        ["report.md", "report-2026-091331.md", "prompt-20260730-091331.md", "report-20260730-091331.txt"],
    )
    def test_ignores_everything_else(self, name):
        assert report_date(name) is None


class TestCreatedMarker:
    def test_roundtrip(self):
        created = datetime(2026, 7, 30, 9, 13, 31)
        assert parse_created_marker(blank_report_content(created)) == created

    def test_survives_content_written_below(self):
        created = datetime(2026, 7, 30, 9, 13, 31)
        text = blank_report_content(created) + "\n# 7/30\n\n* did things\n"
        assert parse_created_marker(text) == created

    def test_absent_marker_is_none(self):
        assert parse_created_marker("# 7/30\n\n* did things\n") is None


class TestBlankDetection:
    def test_fresh_blank_report_is_blank(self):
        assert is_blank_report_text(blank_report_content(datetime(2026, 7, 30)))

    def test_comments_and_whitespace_are_still_blank(self):
        # The user may delete placeholder lines without writing anything.
        assert is_blank_report_text("")
        assert is_blank_report_text("\n  \n")
        assert is_blank_report_text("[//]: # (weekly-report: created 2026-07-30T09:13:31)\n")

    def test_any_real_content_is_filled(self):
        text = blank_report_content(datetime(2026, 7, 30)) + "# 7/30\n* worked\n"
        assert not is_blank_report_text(text)


class TestStripReportMarks:
    def test_removes_marker_and_placeholder_keeps_report(self):
        text = blank_report_content(datetime(2026, 7, 23, 9, 29, 52)) + "# 7/23\n* worked\n"
        assert strip_report_marks(text) == "# 7/23\n* worked"

    def test_plain_report_is_untouched(self):
        assert strip_report_marks("# 7/23\n* worked\n") == "# 7/23\n* worked"


class TestHistory:
    def test_entries_newest_first_and_non_reports_ignored(self, home):
        write_history(home, datetime(2026, 7, 16, 9, 0, 0), datetime(2026, 7, 23, 9, 0, 0))
        (home.history_dir / "notes.md").write_text("not a report", encoding="utf-8")

        manager = ReportFileManager(home, history_limit=5)
        dates = [date for date, _ in manager.history_entries()]
        assert dates == [datetime(2026, 7, 23, 9, 0, 0), datetime(2026, 7, 16, 9, 0, 0)]

    def test_trim_removes_oldest_beyond_limit(self, home):
        write_history(
            home,
            datetime(2026, 7, 9, 9, 0, 0),
            datetime(2026, 7, 16, 9, 0, 0),
            datetime(2026, 7, 23, 9, 0, 0),
        )
        manager = ReportFileManager(home, history_limit=2)
        manager.trim_history()
        dates = [date for date, _ in manager.history_entries()]
        assert dates == [datetime(2026, 7, 23, 9, 0, 0), datetime(2026, 7, 16, 9, 0, 0)]

    def test_import_report(self, home, tmp_path):
        source = tmp_path / "old.md"
        source.write_text("# 7/16\n* stuff\n", encoding="utf-8")

        destination = import_report(home, source, datetime(2026, 7, 16, 9, 0, 0))

        assert destination.name == "report-20260716-090000.md"
        assert destination.read_text(encoding="utf-8") == "# 7/16\n* stuff\n"
        assert source.exists(), "import copies, it does not move"

    def test_import_refuses_to_overwrite(self, home, tmp_path):
        source = tmp_path / "old.md"
        source.write_text("x", encoding="utf-8")
        import_report(home, source, datetime(2026, 7, 16, 9, 0, 0))
        with pytest.raises(FileExistsError):
            import_report(home, source, datetime(2026, 7, 16, 9, 0, 0))


class TestReportMd:
    def test_blank_report_is_not_filled(self, home):
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 30, 9, 13, 31))
        assert not manager.report_md_is_filled()

    def test_marker_beats_mtime(self, home):
        manager = ReportFileManager(home, history_limit=5)
        created = datetime(2026, 7, 23, 9, 29, 52)
        manager.create_blank_report(created=created)
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("# 7/23\n* worked\n")

        date, used_mtime = manager.report_md_date()
        assert date == created
        assert not used_mtime

    def test_mtime_fallback_when_marker_erased(self, home):
        manager = ReportFileManager(home, history_limit=5)
        home.ensure()
        home.report_path.write_text("# 7/23\n* rewritten from scratch\n", encoding="utf-8")
        mtime = datetime(2026, 7, 23, 18, 0, 0)
        os.utime(home.report_path, (mtime.timestamp(), mtime.timestamp()))

        date, used_mtime = manager.report_md_date()
        assert date == mtime
        assert used_mtime


class TestKnownReports:
    def test_filled_report_md_counts_before_archiving(self, home):
        write_history(home, datetime(2026, 7, 16, 9, 0, 0))
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 29, 52))
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("# 7/23\n* worked\n")

        assert manager.last_report_date() == datetime(2026, 7, 23, 9, 29, 52)

    def test_blank_report_md_does_not_count(self, home):
        write_history(home, datetime(2026, 7, 16, 9, 0, 0))
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 29, 52))

        assert manager.last_report_date() == datetime(2026, 7, 16, 9, 0, 0)

    def test_no_reports_at_all(self, home):
        manager = ReportFileManager(home, history_limit=5)
        assert manager.last_report_date() is None

    def test_fetch_report_history_newest_first_up_to_limit(self, home):
        for index, date in enumerate(
            [datetime(2026, 7, 9, 9, 0, 0), datetime(2026, 7, 16, 9, 0, 0), datetime(2026, 7, 23, 9, 0, 0)]
        ):
            write_history(home, date, content=f"report {index}")

        manager = ReportFileManager(home, history_limit=2)
        assert manager.fetch_report_history() == ["report 2", "report 1"]

    def test_fetch_report_history_strips_bookkeeping_marks(self, home):
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 29, 52))
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("# 7/23\n* worked\n")

        assert manager.fetch_report_history() == ["# 7/23\n* worked"]


class TestArchive:
    def test_blank_report_is_discarded(self, home):
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 29, 52))

        assert manager.archive_report_md() is None
        assert not home.report_path.exists()
        assert manager.history_entries() == []

    def test_filled_report_is_archived_under_its_created_date(self, home):
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 29, 52))
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("# 7/23\n* worked\n")

        destination = manager.archive_report_md()

        assert destination is not None
        assert destination.name == "report-20260723-092952.md"
        assert not home.report_path.exists()

    def test_missing_report_md_is_a_no_op(self, home):
        manager = ReportFileManager(home, history_limit=5)
        assert manager.archive_report_md() is None

    def test_same_second_collision_does_not_overwrite(self, home):
        date = datetime(2026, 7, 23, 9, 29, 52)
        write_history(home, date, content="the original")
        manager = ReportFileManager(home, history_limit=5)
        home.report_path.write_text(blank_report_content(date) + "the newcomer\n", encoding="utf-8")

        destination = manager.archive_report_md()

        assert destination.name == "report-20260723-092953.md"
        original = home.history_dir / "report-20260723-092952.md"
        assert original.read_text(encoding="utf-8") == "the original"


class TestWritePhase:
    def test_write_prompt_overwrites_fixed_name(self, home):
        manager = ReportFileManager(home, history_limit=5)
        manager.write_prompt("first")
        path = manager.write_prompt("second")
        assert path == home.prompt_path
        assert home.prompt_path.read_text(encoding="utf-8") == "second"

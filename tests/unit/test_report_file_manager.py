import pytest
import os
from datetime import datetime
from unittest.mock import patch

from weekly_report_prompt.report_file_manager import ReportFileManager
from weekly_report_prompt.const import REPORT_BLANK_MESSAGE, MEMO_BLANK_MESSAGE


class TestReportFileManager:
    """Test cases for ReportFileManager class."""

    def test_initialization_with_build_dir(self, config_loader, build_dir):
        """Test ReportFileManager initialization with provided build directory."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        assert manager.build_dir == build_dir
        assert manager.history_dir == os.path.join(build_dir, "history")
        assert manager.history_limit == 10
        assert os.path.exists(manager.history_dir)

    def test_initialization_with_default_build_dir(self, config_loader, temp_dir):
        """Test ReportFileManager initialization with default build directory."""
        with patch('weekly_report_prompt.report_file_manager.Path') as mock_path:
            mock_path.__file__ = __file__
            mock_path.return_value.parent.parent = temp_dir

            manager = ReportFileManager(config_loader)

            expected_build_dir = os.path.join(temp_dir, "build")
            assert manager.build_dir == expected_build_dir

    def test_initialization_with_invalid_build_dir(self, config_loader):
        """Test ReportFileManager initialization with invalid build directory."""
        with pytest.raises(NotADirectoryError, match="Build directory does not exist"):
            ReportFileManager(config_loader, build_dir="/nonexistent/directory")

    def test_get_today_str(self, config_loader, build_dir):
        """Test getting today's date string."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        with patch('weekly_report_prompt.report_file_manager.datetime') as mock_datetime:
            mock_now = datetime(2025, 9, 15, 14, 30, 45)
            mock_datetime.now.return_value = mock_now
            # datetime 클래스 자체를 mock에서 가져오도록 설정
            mock_datetime.strftime = datetime.strftime

            today_str = manager.get_today_str()
            assert today_str == "20250915-143045"

    def test_save_prompt(self, config_loader, build_dir):
        """Test saving prompt to file."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)
        prompt_content = "# Test Prompt\n\nThis is a test prompt."

        with patch.object(manager, 'get_today_str', return_value="20250915-143045"):
            file_path = manager.save_prompt(prompt_content)

        expected_filename = "prompt-20250915-143045.md"
        expected_path = os.path.join(build_dir, expected_filename)

        assert file_path == expected_path
        assert manager.prompt_file_path == expected_path

        # Verify file was created with correct content
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == prompt_content

    def test_create_report_file(self, config_loader, build_dir):
        """Test creating a new report file."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        with patch.object(manager, 'get_today_str', return_value="20250915-143045"):
            file_path = manager.create_report_file()

        expected_filename = "report-20250915-143045.md"
        expected_path = os.path.join(build_dir, expected_filename)

        assert file_path == expected_path

        # Verify file was created with blank message
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == REPORT_BLANK_MESSAGE

    def test_move_previous_reports(self, config_loader, build_dir):
        """Test moving previous reports to history directory."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        # Create some test report files
        report1_path = os.path.join(build_dir, "report-20250910-100000.md")
        report2_path = os.path.join(build_dir, "report-20250911-110000.md")
        other_file_path = os.path.join(build_dir, "other-file.md")

        # Create files with different content
        with open(report1_path, "w", encoding="utf-8") as f:
            f.write("# Completed Report 1")

        with open(report2_path, "w", encoding="utf-8") as f:
            f.write(REPORT_BLANK_MESSAGE)  # Blank report

        with open(other_file_path, "w", encoding="utf-8") as f:
            f.write("Not a report file")

        manager.move_previous_reports()

        # Check that completed report was moved to history
        history_report1 = os.path.join(manager.history_dir, "report-20250910-100000.md")
        assert os.path.exists(history_report1)
        assert not os.path.exists(report1_path)

        # Check that blank report was deleted
        assert not os.path.exists(report2_path)

        # Check that other file was not touched
        assert os.path.exists(other_file_path)

    def test_move_previous_reports_with_history_limit(self, config_loader, build_dir):
        """Test moving reports with history limit enforcement."""
        # Create config with lower history limit
        config_loader.settings.report_history_limit = 2
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        # Create old history files that exceed the limit
        old_files = [
            "report-20250901-100000.md",
            "report-20250902-100000.md",
            "report-20250903-100000.md"
        ]

        for filename in old_files:
            file_path = os.path.join(manager.history_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Old Report")

        # Create new report to move
        new_report_path = os.path.join(build_dir, "report-20250915-100000.md")
        with open(new_report_path, "w", encoding="utf-8") as f:
            f.write("# New Report")

        manager.move_previous_reports()

        # Check that old files were cleaned up (only 2 should remain + new one = 3 total)
        history_files = [f for f in os.listdir(manager.history_dir) if f.startswith("report-")]
        assert len(history_files) <= manager.history_limit

        # New report should be in history
        new_history_path = os.path.join(manager.history_dir, "report-20250915-100000.md")
        assert os.path.exists(new_history_path)

    def test_fetch_report_history_respects_the_history_limit(self, config_loader, build_dir):
        """The limit bounds what the prompt carries, not just what cleanup keeps."""
        config_loader.settings.report_history_limit = 2
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        history_files = [
            ("report-20250910-100000.md", "# Report 1"),
            ("report-20250911-100000.md", "# Report 2"),
            ("report-20250912-100000.md", "# Report 3")
        ]

        for filename, content in history_files:
            file_path = os.path.join(manager.history_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        assert manager.fetch_report_history() == ["# Report 3", "# Report 2"]

    def test_fetch_memo_does_not_create_the_memo_file(self, config_loader, build_dir):
        """Reading the memo is read-only; a dry run must not leave a file behind."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        assert manager.fetch_memo() is None
        assert not os.path.exists(os.path.join(build_dir, "memo.md"))

    def test_ensure_memo_file_recreates_the_placeholder(self, config_loader, build_dir):
        """Test that the memo placeholder comes back if it was deleted."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        memo_path = manager.ensure_memo_file()

        assert os.path.exists(memo_path)
        with open(memo_path, "r", encoding="utf-8") as f:
            assert f.read() == MEMO_BLANK_MESSAGE

    def test_fetch_report_history(self, config_loader, build_dir):
        """History is ordered by report date, not by how the contents happen to sort.

        The headings below are deliberately chosen so that sorting the file *contents*
        descending ("# 6/4" > "# 6/25" > "# 6/11") disagrees with real date order.
        """
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        history_files = [
            ("report-20260604-092902.md", "# 6/4"),
            ("report-20260611-110353.md", "# 6/11"),
            ("report-20260625-085641.md", "# 6/25"),
        ]

        for filename, content in history_files:
            file_path = os.path.join(manager.history_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        history = manager.fetch_report_history()

        assert history == ["# 6/25", "# 6/11", "# 6/4"]

    def test_fetch_report_history_ignores_unrelated_files(self, config_loader, build_dir):
        """Files that do not carry a report timestamp are not treated as history."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        for filename in ["report-20260604-092902.md", "report-draft.md", "notes.md"]:
            file_path = os.path.join(manager.history_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"content of {filename}")

        assert manager.fetch_report_history() == ["content of report-20260604-092902.md"]

    def test_fetch_report_history_empty(self, config_loader, build_dir):
        """Test fetching report history when no reports exist."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        history = manager.fetch_report_history()
        assert history == []

    def test_get_last_report_date(self, config_loader, build_dir):
        """Test getting the last report date."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        # Create history files with different dates
        history_files = [
            "report-20250910-100000.md",
            "report-20250915-120000.md",
            "report-20250912-110000.md"
        ]

        for filename in history_files:
            file_path = os.path.join(manager.history_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# Test Report")

        last_date = manager.get_last_report_date()

        # Should return the latest date (20250915-120000)
        expected_date = datetime(2025, 9, 15, 12, 0, 0)
        assert last_date == expected_date

    def test_get_last_report_date_no_reports(self, config_loader, build_dir):
        """Test getting last report date when no reports exist."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        last_date = manager.get_last_report_date()
        assert last_date is None

    def test_get_last_report_date_counts_a_report_not_yet_archived(self, config_loader, build_dir):
        """A filled-in report in the build dir marks the period, before it is archived.

        main() reads the date before it moves anything, so this must not depend on
        move_previous_reports() having run first.
        """
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        with open(os.path.join(manager.history_dir, "report-20250910-100000.md"), "w") as f:
            f.write("# Archived report")
        with open(os.path.join(build_dir, "report-20250917-120000.md"), "w") as f:
            f.write("# This week, already written up")

        assert manager.get_last_report_date() == datetime(2025, 9, 17, 12, 0, 0)

    def test_get_last_report_date_ignores_a_blank_report(self, config_loader, build_dir):
        """A blank report was never written up, so it does not close out a period."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        with open(os.path.join(manager.history_dir, "report-20250910-100000.md"), "w") as f:
            f.write("# Archived report")
        with open(os.path.join(build_dir, "report-20250917-120000.md"), "w") as f:
            f.write(REPORT_BLANK_MESSAGE)

        assert manager.get_last_report_date() == datetime(2025, 9, 10, 10, 0, 0)

    def test_fetch_report_history_includes_a_report_not_yet_archived(self, config_loader, build_dir):
        """The prompt must show last week's report even though it is still in build/."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        with open(os.path.join(manager.history_dir, "report-20250910-100000.md"), "w") as f:
            f.write("# older")
        with open(os.path.join(build_dir, "report-20250917-120000.md"), "w") as f:
            f.write("# newest, not archived yet")

        assert manager.fetch_report_history() == [
            "# newest, not archived yet",
            "# older",
        ]

    def test_clear_previous_prompts(self, config_loader, build_dir):
        """Test clearing previous prompt files."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        # Create some prompt files and other files
        prompt_files = [
            "prompt-20250910-100000.md",
            "prompt-20250911-110000.md"
        ]
        other_files = [
            "report-20250910-100000.md",
            "other-file.txt"
        ]

        for filename in prompt_files + other_files:
            file_path = os.path.join(build_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("test content")

        manager.clear_previous_prompts()

        # Check that prompt files were deleted
        for filename in prompt_files:
            file_path = os.path.join(build_dir, filename)
            assert not os.path.exists(file_path)

        # Check that other files remain
        for filename in other_files:
            file_path = os.path.join(build_dir, filename)
            assert os.path.exists(file_path)

    def test_fetch_memo(self, config_loader, build_dir):
        """Test fetching memo content."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        memo_content = "# Weekly Notes\n\n- Important task completed\n- Next week planning"
        memo_path = os.path.join(build_dir, "memo.md")

        with open(memo_path, "w", encoding="utf-8") as f:
            f.write(memo_content)

        result = manager.fetch_memo()
        assert result == memo_content

    def test_fetch_memo_not_exists(self, config_loader, build_dir):
        """Test fetching memo when file doesn't exist."""
        manager = ReportFileManager(config_loader, build_dir=build_dir)

        result = manager.fetch_memo()
        assert result is None

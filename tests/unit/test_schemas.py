from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from weekly_report_prompt.schemas import AppConfig, CommitData, CommitDataSummary, CommitStats


class TestAppConfig:
    """Test cases for AppConfig model."""

    def test_the_default_large_prompt_threshold_can_actually_fire(self):
        """A real prompt runs ~30k tokens; the old hard-coded 1_000_000 never warned.

        The value is advisory and configurable -- this only pins the default to
        something a prompt can plausibly reach.
        """
        assert AppConfig(author="Test Author").large_prompt_tokens <= 200_000

    def test_report_history_limit_must_keep_at_least_one_report(self):
        """Zero reaches the slice that deletes archived reports and empties build/history.

        Nothing else records which periods have been reported on, and Git does not
        track the archive, so the deletion is unrecoverable and silent.
        """
        with pytest.raises(ValidationError):
            AppConfig(author="Test Author", report_history_limit=0)

    def test_max_diff_lines_rejects_negative_values(self):
        """`lines[:-2]` drops the last two lines of every diff and reports "showing -2"."""
        with pytest.raises(ValidationError):
            AppConfig(author="Test Author", max_diff_lines=-1)

    def test_max_diff_lines_allows_zero(self):
        """Unlike the history limit, zero here is a real choice: commit messages, no diffs."""
        assert AppConfig(author="Test Author", max_diff_lines=0).max_diff_lines == 0

    def test_large_prompt_tokens_must_be_positive(self):
        """A threshold of zero warns on every run, which trains you to ignore the warning."""
        with pytest.raises(ValidationError):
            AppConfig(author="Test Author", large_prompt_tokens=0)


class TestCommitStats:
    """Test cases for CommitStats model."""

    def test_commit_stats_creation(self):
        """Test creating CommitStats with valid data."""
        stats = CommitStats(insertions=10, deletions=5, changed_files=["a.py", "b.py"])

        assert stats.insertions == 10
        assert stats.deletions == 5
        assert stats.changed_files == ["a.py", "b.py"]

    def test_commit_stats_validation(self):
        """Test CommitStats validation with invalid data."""
        with pytest.raises(ValueError):
            CommitStats(insertions="invalid", deletions=5, changed_files=[])


class TestCommitData:
    """Test cases for CommitData model."""

    def test_commit_data_creation(self, sample_commit_data):
        """Test creating CommitData with valid data."""
        commit = sample_commit_data

        assert commit.id == "abc123def456"
        assert commit.author == "Test Author"
        assert commit.email == "test@example.com"
        assert commit.message == "Add new feature\n\nDetailed description of the feature"
        assert commit.stats.insertions == 15
        assert commit.stats.deletions == 5
        assert commit.stats.changed_files == ["a.py", "b.py", "c.py"]
        assert commit.diff == "@@ -1,3 +1,3 @@\n-old line\n+new line"

    def test_from_commit_class_method(self):
        """Test creating CommitData from git commit object."""
        # Mock git commit object
        mock_commit = Mock()
        mock_commit.hexsha = "abc123def456"
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.committed_datetime = datetime(2025, 9, 15, 10, 30, 0, tzinfo=UTC)
        mock_commit.message = "Test commit message  \n  "  # With trailing whitespace
        mock_commit.stats.total = {"insertions": 20, "deletions": 10, "files": 2}
        # GitPython keys this dict by path; the summary needs the paths, not the count.
        mock_commit.stats.files = {"src/b.py": {}, "src/a.py": {}}

        diff_content = "sample diff content"

        commit_data = CommitData.from_commit(mock_commit, diff_content)

        assert commit_data.id == "abc123def456"
        assert commit_data.author == "Test Author"
        assert commit_data.email == "test@example.com"
        assert commit_data.message == "Test commit message"  # Whitespace should be stripped
        assert commit_data.stats.insertions == 20
        assert commit_data.stats.deletions == 10
        assert commit_data.stats.changed_files == ["src/a.py", "src/b.py"]
        assert commit_data.diff == "sample diff content"


class TestCommitDataSummary:
    """Test cases for CommitDataSummary model."""

    def test_commit_data_summary_creation(self):
        """Test creating CommitDataSummary with valid data."""
        start_date = datetime(2025, 9, 10, tzinfo=UTC)
        end_date = datetime(2025, 9, 17, tzinfo=UTC)

        summary = CommitDataSummary(
            start_date=start_date,
            end_date=end_date,
            total_commits=5,
            total_insertions=100,
            total_deletions=50,
            total_files_changed=15,
        )

        assert summary.start_date == start_date
        assert summary.end_date == end_date
        assert summary.total_commits == 5
        assert summary.total_insertions == 100
        assert summary.total_deletions == 50
        assert summary.total_files_changed == 15

    def test_commit_data_summary_validation(self):
        """Test CommitDataSummary validation with invalid data."""
        start_date = datetime(2025, 9, 10, tzinfo=UTC)
        end_date = datetime(2025, 9, 17, tzinfo=UTC)

        with pytest.raises(ValueError):
            CommitDataSummary(
                start_date=start_date,
                end_date=end_date,
                total_commits="invalid",  # Should be int
                total_insertions=100,
                total_deletions=50,
                total_files_changed=15,
            )

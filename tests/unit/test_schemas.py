import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from weekly_report_prompt.schemas import CommitData, CommitStats, CommitDataSummary


class TestCommitStats:
    """Test cases for CommitStats model."""

    def test_commit_stats_creation(self):
        """Test creating CommitStats with valid data."""
        stats = CommitStats(insertions=10, deletions=5, files=3)

        assert stats.insertions == 10
        assert stats.deletions == 5
        assert stats.files == 3

    def test_commit_stats_validation(self):
        """Test CommitStats validation with invalid data."""
        with pytest.raises(ValueError):
            CommitStats(insertions="invalid", deletions=5, files=3)


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
        assert commit.stats.files == 3
        assert commit.diff == "@@ -1,3 +1,3 @@\n-old line\n+new line"

    def test_from_commit_class_method(self):
        """Test creating CommitData from git commit object."""
        # Mock git commit object
        mock_commit = Mock()
        mock_commit.hexsha = "abc123def456"
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.committed_datetime = datetime(2025, 9, 15, 10, 30, 0, tzinfo=timezone.utc)
        mock_commit.message = "Test commit message  \n  "  # With trailing whitespace
        mock_commit.stats.total = {
            "insertions": 20,
            "deletions": 10,
            "files": 5
        }

        diff_content = "sample diff content"

        commit_data = CommitData.from_commit(mock_commit, diff_content)

        assert commit_data.id == "abc123def456"
        assert commit_data.author == "Test Author"
        assert commit_data.email == "test@example.com"
        assert commit_data.message == "Test commit message"  # Whitespace should be stripped
        assert commit_data.stats.insertions == 20
        assert commit_data.stats.deletions == 10
        assert commit_data.stats.files == 5
        assert commit_data.diff == "sample diff content"


class TestCommitDataSummary:
    """Test cases for CommitDataSummary model."""

    def test_commit_data_summary_creation(self):
        """Test creating CommitDataSummary with valid data."""
        start_date = datetime(2025, 9, 10, tzinfo=timezone.utc)
        end_date = datetime(2025, 9, 17, tzinfo=timezone.utc)

        summary = CommitDataSummary(
            start_date=start_date,
            end_date=end_date,
            total_commits=5,
            total_insertions=100,
            total_deletions=50,
            total_files_changed=15
        )

        assert summary.start_date == start_date
        assert summary.end_date == end_date
        assert summary.total_commits == 5
        assert summary.total_insertions == 100
        assert summary.total_deletions == 50
        assert summary.total_files_changed == 15

    def test_commit_data_summary_validation(self):
        """Test CommitDataSummary validation with invalid data."""
        start_date = datetime(2025, 9, 10, tzinfo=timezone.utc)
        end_date = datetime(2025, 9, 17, tzinfo=timezone.utc)

        with pytest.raises(ValueError):
            CommitDataSummary(
                start_date=start_date,
                end_date=end_date,
                total_commits="invalid",  # Should be int
                total_insertions=100,
                total_deletions=50,
                total_files_changed=15
            )

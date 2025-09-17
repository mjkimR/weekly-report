import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import git

from weekly_report_prompt.git_data_collector import GitDataCollector
from weekly_report_prompt.schemas import CommitData


class TestGitDataCollector:
    """Test cases for GitDataCollector class."""

    def test_initialization(self, config_loader):
        """Test GitDataCollector initialization."""
        with patch('weekly_report_prompt.git_data_collector.git.Repo') as mock_repo:
            collector = GitDataCollector(config_loader, "/test/repo/path")

            assert collector.config_loader == config_loader
            assert collector.author == "Test Author"
            mock_repo.assert_called_once_with("/test/repo/path")

    def test_initialization_default_repo_path(self, config_loader):
        """Test GitDataCollector initialization with default repo path."""
        with patch('weekly_report_prompt.git_data_collector.git.Repo') as mock_repo:
            collector = GitDataCollector(config_loader)

            mock_repo.assert_called_once_with(".")

    @patch('weekly_report_prompt.git_data_collector.git.Repo')
    def test_collect_commits(self, mock_repo_class, config_loader):
        """Test collecting commits from repository."""
        # Setup mock repository
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Create mock commits
        mock_commit1 = Mock()
        mock_commit1.hexsha = "abc123"
        mock_commit1.author.name = "Test Author"
        mock_commit1.author.email = "test@example.com"
        mock_commit1.parents = []  # Not a merge commit
        mock_commit1.stats.total = {"insertions": 10, "deletions": 5, "files": 2}
        mock_commit1.committed_datetime = datetime(2025, 9, 15, tzinfo=timezone.utc)
        mock_commit1.message = "Test commit"

        mock_commit2 = Mock()
        mock_commit2.hexsha = "def456"
        mock_commit2.author.name = "Other Author"  # Different author
        mock_commit2.author.email = "other@example.com"
        mock_commit2.parents = []

        mock_commit3 = Mock()
        mock_commit3.hexsha = "ghi789"
        mock_commit3.author.name = "Test Author"
        mock_commit3.author.email = "test@example.com"
        mock_commit3.parents = [Mock(), Mock()]  # Merge commit (should be excluded)

        mock_repo.iter_commits.return_value = [mock_commit1, mock_commit2, mock_commit3]

        collector = GitDataCollector(config_loader)

        # Mock get_commit_diff method
        with patch.object(collector, 'get_commit_diff', return_value="test diff"):
            since_date = datetime(2025, 9, 10, tzinfo=timezone.utc)
            commits = collector.collect_commits(since_date)

        # Should only return commit1 (matching author, not merge commit)
        assert len(commits) == 1
        assert commits[0].id == "abc123"
        assert commits[0].author == "Test Author"

        mock_repo.iter_commits.assert_called_once_with(since=since_date)

    @patch('weekly_report_prompt.git_data_collector.git.Repo')
    def test_get_commit_diff_with_parents(self, mock_repo_class, config_loader):
        """Test getting diff for commit with parents."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Mock commit with parent
        mock_commit = Mock()
        mock_parent = Mock()
        mock_commit.parents = [mock_parent]

        mock_repo.commit.return_value = mock_commit
        mock_repo.git.diff.return_value = "sample diff content"

        collector = GitDataCollector(config_loader)
        diff = collector.get_commit_diff("abc123")

        assert diff == "sample diff content"
        mock_repo.commit.assert_called_once_with("abc123")
        mock_repo.git.diff.assert_called_once_with(mock_parent, mock_commit)

    @patch('weekly_report_prompt.git_data_collector.git.Repo')
    @patch('weekly_report_prompt.git_data_collector.git.NULL_TREE')
    def test_get_commit_diff_without_parents(self, mock_null_tree, mock_repo_class, config_loader):
        """Test getting diff for commit without parents (initial commit)."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Mock commit without parents
        mock_commit = Mock()
        mock_commit.parents = []

        mock_repo.commit.return_value = mock_commit
        mock_repo.git.diff.return_value = "initial commit diff"

        collector = GitDataCollector(config_loader)
        diff = collector.get_commit_diff("abc123")

        assert diff == "initial commit diff"
        mock_repo.commit.assert_called_once_with("abc123")
        mock_repo.git.diff.assert_called_once_with(mock_null_tree, mock_commit)

    @patch('weekly_report_prompt.git_data_collector.git.Repo')
    def test_collect_commits_empty_result(self, mock_repo_class, config_loader):
        """Test collecting commits when no commits match criteria."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Mock commits that don't match criteria
        mock_commit1 = Mock()
        mock_commit1.author.name = "Other Author"  # Different author
        mock_commit1.parents = []

        mock_commit2 = Mock()
        mock_commit2.author.name = "Test Author"
        mock_commit2.parents = [Mock(), Mock()]  # Merge commit

        mock_repo.iter_commits.return_value = [mock_commit1, mock_commit2]

        collector = GitDataCollector(config_loader)
        since_date = datetime(2025, 9, 10, tzinfo=timezone.utc)
        commits = collector.collect_commits(since_date)

        assert len(commits) == 0

    @patch('weekly_report_prompt.git_data_collector.git.Repo')
    def test_collect_commits_integration_with_commit_data(self, mock_repo_class, config_loader):
        """Test that collect_commits properly creates CommitData objects."""
        mock_repo = Mock()
        mock_repo_class.return_value = mock_repo

        # Create a realistic mock commit
        mock_commit = Mock()
        mock_commit.hexsha = "abc123def456"
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.committed_datetime = datetime(2025, 9, 15, 10, 30, 0, tzinfo=timezone.utc)
        mock_commit.message = "Add new feature\n\nDetailed description"
        mock_commit.parents = []
        mock_commit.stats.total = {
            "insertions": 15,
            "deletions": 5,
            "files": 3
        }

        mock_repo.iter_commits.return_value = [mock_commit]

        collector = GitDataCollector(config_loader)

        # Mock get_commit_diff
        with patch.object(collector, 'get_commit_diff', return_value="test diff content"):
            since_date = datetime(2025, 9, 10, tzinfo=timezone.utc)
            commits = collector.collect_commits(since_date)

        assert len(commits) == 1
        commit_data = commits[0]

        # Verify CommitData object is properly created
        assert isinstance(commit_data, CommitData)
        assert commit_data.id == "abc123def456"
        assert commit_data.author == "Test Author"
        assert commit_data.email == "test@example.com"
        assert commit_data.message == "Add new feature\n\nDetailed description"
        assert commit_data.stats.insertions == 15
        assert commit_data.stats.deletions == 5
        assert commit_data.stats.files == 3
        assert commit_data.diff == "test diff content"

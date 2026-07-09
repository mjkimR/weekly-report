import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from weekly_report_prompt.prompt_generator import PromptGenerator, fenced
from weekly_report_prompt.schemas import CommitData, CommitStats, CommitDataSummary


class TestFenced:
    """Test cases for the fenced() helper."""

    def test_plain_content_gets_a_three_backtick_fence(self):
        assert fenced("hello", "markdown") == "```markdown\nhello\n```"

    def test_inline_code_does_not_grow_the_fence(self):
        assert fenced("use `x` here") == "```\nuse `x` here\n```"

    def test_the_fence_outgrows_the_longest_run_inside_the_content(self):
        """A fence no longer than the content's own would end the block early."""
        assert fenced("a ``` b", "md") == "````md\na ``` b\n````"
        assert fenced("a ````` b", "md") == "``````md\na ````` b\n``````"


class TestPromptGenerator:
    """Test cases for PromptGenerator class."""

    @pytest.fixture
    def sample_project_data(self, sample_commit_data):
        """Provide sample project data for testing."""
        summary = CommitDataSummary(
            start_date=datetime(2025, 9, 10, tzinfo=timezone.utc),
            end_date=datetime(2025, 9, 17, tzinfo=timezone.utc),
            total_commits=2,
            total_insertions=25,
            total_deletions=10,
            total_files_changed=5
        )

        return [
            {
                "project_name": "test-project",
                "summary": summary,
                "recent_commits": [sample_commit_data]
            }
        ]

    def test_initialization(self, sample_project_data, config_loader):
        """Test PromptGenerator initialization."""
        previous_reports = ["Previous report 1", "Previous report 2"]
        memo = "Test memo content"

        generator = PromptGenerator(
            project_data=sample_project_data,
            config_loader=config_loader,
            previous_reports=previous_reports,
            memo=memo
        )

        assert generator.project_data == sample_project_data
        assert generator.config_loader == config_loader
        assert generator.previous_reports == previous_reports
        assert generator.memo == memo
        assert generator.max_diff_lines == 25
        assert generator.lang == "ko"

    def test_initialization_with_defaults(self, sample_project_data, config_loader):
        """Test PromptGenerator initialization with default values."""
        generator = PromptGenerator(
            project_data=sample_project_data,
            config_loader=config_loader
        )

        assert generator.previous_reports == []
        assert generator.memo is None

    def test_format_commit_with_diff(self, config_loader, sample_commit_data):
        """Test formatting a single commit with diff."""
        generator = PromptGenerator([], config_loader)

        formatted = generator._format_commit(sample_commit_data, include_diff=True)

        assert "**Add new feature**" in formatted
        assert "abc123d" in formatted  # Short commit ID
        assert "2025-09-15" in formatted
        assert "Detailed description of the feature" in formatted
        assert "```diff" in formatted
        assert "@@ -1,3 +1,3 @@" in formatted

    def test_format_commit_without_diff(self, config_loader, sample_commit_data):
        """Test formatting a single commit without diff."""
        generator = PromptGenerator([], config_loader)

        formatted = generator._format_commit(sample_commit_data, include_diff=False)

        assert "**Add new feature**" in formatted
        assert "abc123d" in formatted
        assert "2025-09-15" in formatted
        assert "```diff" not in formatted

    def test_format_commit_with_long_diff(self, config_loader):
        """Test formatting commit with diff exceeding max lines."""
        # Create commit with long diff
        long_diff = "\n".join([f"+ line {i}" for i in range(50)])
        commit_data = CommitData(
            id="abc123def456",
            author="Test Author",
            email="test@example.com",
            date=datetime(2025, 9, 15, tzinfo=timezone.utc),
            message="Test commit",
            stats=CommitStats(insertions=50, deletions=0, changed_files=["big.py"]),
            diff=long_diff
        )

        generator = PromptGenerator([], config_loader)
        formatted = generator._format_commit(commit_data, include_diff=True)

        assert "Some diff lines omitted" in formatted
        assert f"showing {generator.max_diff_lines} of 50 total lines" in formatted

    def test_format_commits_empty_list(self, config_loader):
        """Test formatting empty commits list."""
        generator = PromptGenerator([], config_loader)

        formatted = generator._format_commits([])
        assert formatted == "  - None"

    def test_format_commits_with_multiple_commits(self, config_loader, sample_commit_data):
        """Test formatting multiple commits."""
        commit2 = CommitData(
            id="def456ghi789",
            author="Test Author",
            email="test@example.com",
            date=datetime(2025, 9, 16, tzinfo=timezone.utc),
            message="Fix bug",
            stats=CommitStats(insertions=5, deletions=2, changed_files=["bug.py"]),
            diff="@@ -5,1 +5,1 @@\n-old bug\n+fixed bug"
        )

        generator = PromptGenerator([], config_loader)
        formatted = generator._format_commits([sample_commit_data, commit2])

        assert "**Add new feature**" in formatted
        assert "**Fix bug**" in formatted
        assert "abc123d" in formatted
        assert "def456g" in formatted

    def test_generate_prompt_basic(self, sample_project_data, config_loader):
        """Test generating basic prompt without optional elements."""
        generator = PromptGenerator(sample_project_data, config_loader)

        prompt = generator.generate_prompt()

        # Check main sections
        assert "# Weekly Work Report Request" in prompt
        assert "## 📑 Template" in prompt
        assert "## 📊 [test-project] This Week's Git Activity Summary" in prompt
        assert "## 🚀 [test-project] Main Progress This Week" in prompt
        assert "## 📄 Report Writing Instructions" in prompt

        # Check project data content
        assert "Total commits: 2" in prompt
        assert "Total lines added: 25" in prompt
        assert "Total lines deleted: 10" in prompt
        assert "Number of files changed: 5" in prompt
        assert "**Add new feature**" in prompt

    def test_generate_prompt_with_previous_reports(self, sample_project_data, config_loader):
        """Test generating prompt with previous reports."""
        previous_reports = ["Previous report 1", "Previous report 2"]
        generator = PromptGenerator(
            sample_project_data,
            config_loader,
            previous_reports=previous_reports
        )

        prompt = generator.generate_prompt()

        assert "## 📜 Previous Weekly Reports" in prompt
        assert "Previous report 1" in prompt
        assert "Previous report 2" in prompt

    def test_previous_reports_are_fenced_rather_than_flattened(self, sample_project_data, config_loader):
        """A report is a markdown document, not a bullet.

        The old code emitted `- {report}`, which indented only the first line and left
        the report's own headings and bullets to run together with the prompt's.
        """
        report = "# Week of 6/25\n\n## Done\n\n* shipped the thing\n* fixed the bug"
        generator = PromptGenerator(
            sample_project_data, config_loader, previous_reports=[report]
        )

        prompt = generator.generate_prompt()

        assert f"```markdown\n{report}\n```" in prompt
        assert "- # Week of 6/25" not in prompt

    def test_a_report_containing_a_fence_stays_inside_its_own_fence(self, sample_project_data, config_loader):
        """Reports quote code, so the wrapping fence has to be longer than theirs."""
        report = "# Week\n\n```python\nprint('hi')\n```"
        generator = PromptGenerator(
            sample_project_data, config_loader, previous_reports=[report]
        )

        prompt = generator.generate_prompt()

        assert f"````markdown\n{report}\n````" in prompt

    def test_each_previous_report_gets_its_own_fence(self, sample_project_data, config_loader):
        generator = PromptGenerator(
            sample_project_data, config_loader, previous_reports=["# a", "# b"]
        )

        prompt = generator.generate_prompt()

        assert "```markdown\n# a\n```\n\n```markdown\n# b\n```" in prompt

    def test_generate_prompt_with_memo(self, sample_project_data, config_loader):
        """Test generating prompt with memo."""
        memo = "Important notes for this week:\n- Task A completed\n- Task B in progress"
        generator = PromptGenerator(
            sample_project_data,
            config_loader,
            memo=memo
        )

        prompt = generator.generate_prompt()

        assert "## 📝 Memo" in prompt
        assert "Important notes for this week:" in prompt
        assert "Task A completed" in prompt

    def test_generate_prompt_without_diff(self, sample_project_data, config_loader):
        """Test generating prompt without diff content."""
        generator = PromptGenerator(sample_project_data, config_loader)

        prompt = generator.generate_prompt(should_include_diff=False)

        assert "**Add new feature**" in prompt
        assert "```diff" not in prompt

    def test_generate_prompt_with_empty_summary(self, config_loader, sample_commit_data):
        """Test generating prompt with empty summary."""
        project_data = [
            {
                "project_name": "empty-project",
                "summary": None,
                "recent_commits": [sample_commit_data]
            }
        ]

        generator = PromptGenerator(project_data, config_loader)
        prompt = generator.generate_prompt()

        assert "No Git activity summary information for this period" in prompt

    def test_generate_prompt_with_multiple_projects(self, config_loader, sample_commit_data):
        """Test generating prompt with multiple projects."""
        summary1 = CommitDataSummary(
            start_date=datetime(2025, 9, 10, tzinfo=timezone.utc),
            end_date=datetime(2025, 9, 17, tzinfo=timezone.utc),
            total_commits=1,
            total_insertions=15,
            total_deletions=5,
            total_files_changed=3
        )

        summary2 = CommitDataSummary(
            start_date=datetime(2025, 9, 10, tzinfo=timezone.utc),
            end_date=datetime(2025, 9, 17, tzinfo=timezone.utc),
            total_commits=2,
            total_insertions=30,
            total_deletions=15,
            total_files_changed=8
        )

        project_data = [
            {
                "project_name": "project-1",
                "summary": summary1,
                "recent_commits": [sample_commit_data]
            },
            {
                "project_name": "project-2",
                "summary": summary2,
                "recent_commits": []
            }
        ]

        generator = PromptGenerator(project_data, config_loader)
        prompt = generator.generate_prompt()

        assert "[project-1]" in prompt
        assert "[project-2]" in prompt
        assert "Total commits: 1" in prompt
        assert "Total commits: 2" in prompt
        assert "- None" in prompt  # Empty commits for project-2

    @patch('weekly_report_prompt.prompt_generator.tiktoken')
    def test_count_approximate_tokens(self, mock_tiktoken, config_loader):
        """Test counting approximate tokens."""
        mock_encoding = Mock()
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
        mock_tiktoken.encoding_for_model.return_value = mock_encoding

        generator = PromptGenerator([], config_loader)

        token_count = generator.count_approximate_tokens("test text", "gpt-4")

        assert token_count == 5
        mock_tiktoken.encoding_for_model.assert_called_once_with("gpt-4")
        mock_encoding.encode.assert_called_once_with("test text")

    @patch('weekly_report_prompt.prompt_generator.tiktoken')
    def test_count_approximate_tokens_estimates_when_the_encoding_will_not_load(
        self, mock_tiktoken, config_loader
    ):
        """tiktoken downloads on first use; an offline run must not lose the prompt."""
        mock_tiktoken.encoding_for_model.side_effect = ConnectionError("offline")

        generator = PromptGenerator([], config_loader)

        assert generator.count_approximate_tokens("a" * 400) == 100

    def test_generate_prompt_language_instruction(self, sample_project_data, config_loader):
        """Test that language instruction is included in prompt."""
        generator = PromptGenerator(sample_project_data, config_loader)

        prompt = generator.generate_prompt()

        assert f"must be written in '{config_loader.get_lang()}' language" in prompt

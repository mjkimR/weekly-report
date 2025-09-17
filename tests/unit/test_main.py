import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from weekly_report_prompt.main import main, summarize_commit_data
from weekly_report_prompt.schemas import CommitData, CommitStats, CommitDataSummary


class TestSummarizeCommitData:
    """Test cases for summarize_commit_data function."""

    def test_summarize_commit_data_with_commits(self, sample_commit_data):
        """Test summarizing commit data with actual commits."""
        commit2 = CommitData(
            id="def456ghi789",
            author="Test Author",
            email="test@example.com",
            date=datetime(2025, 9, 16, tzinfo=timezone.utc),
            message="Fix bug",
            stats=CommitStats(insertions=5, deletions=2, files=1),
            diff="test diff"
        )

        commits = [sample_commit_data, commit2]
        summary = summarize_commit_data(commits)

        assert isinstance(summary, CommitDataSummary)
        assert summary.start_date == datetime(2025, 9, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert summary.end_date == datetime(2025, 9, 16, tzinfo=timezone.utc)
        assert summary.total_commits == 2
        assert summary.total_insertions == 20  # 15 + 5
        assert summary.total_deletions == 7   # 5 + 2
        assert summary.total_files_changed == 4  # 3 + 1

    def test_summarize_commit_data_empty_list(self):
        """Test summarizing empty commit data."""
        with patch('weekly_report_prompt.main.datetime') as mock_datetime:
            mock_now = datetime(2025, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now

            summary = summarize_commit_data([])

            assert summary.total_commits == 0
            assert summary.total_insertions == 0
            assert summary.total_deletions == 0
            assert summary.total_files_changed == 0
            assert summary.start_date == mock_now
            assert summary.end_date == mock_now

    def test_summarize_commit_data_single_commit(self, sample_commit_data):
        """Test summarizing single commit data."""
        summary = summarize_commit_data([sample_commit_data])

        assert summary.total_commits == 1
        assert summary.total_insertions == 15
        assert summary.total_deletions == 5
        assert summary.total_files_changed == 3
        assert summary.start_date == summary.end_date == sample_commit_data.date


class TestMain:
    """Test cases for main function."""

    @patch('weekly_report_prompt.main.Console')
    @patch('weekly_report_prompt.main.ConfigLoader')
    @patch('weekly_report_prompt.main.ReportFileManager')
    @patch('weekly_report_prompt.main.GitDataCollector')
    @patch('weekly_report_prompt.main.PromptGenerator')
    def test_main_function_success_flow(
        self,
        mock_prompt_gen_class,
        mock_git_collector_class,
        mock_file_mgr_class,
        mock_config_class,
        mock_console_class,
        sample_commit_data
    ):
        """Test successful execution of main function."""
        # Setup mocks
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        mock_config = Mock()
        mock_config.get_repositories.return_value = ["/path/to/repo1", "/path/to/repo2"]
        mock_config_class.return_value = mock_config

        mock_file_mgr = Mock()
        mock_file_mgr.get_last_report_date.return_value = datetime(2025, 9, 10, tzinfo=timezone.utc)
        mock_file_mgr.fetch_report_history.return_value = ["Previous report"]
        mock_file_mgr.fetch_memo.return_value = "Test memo"
        mock_file_mgr.prompt_file_path = "/path/to/prompt.md"
        mock_file_mgr_class.return_value = mock_file_mgr

        mock_git_collector = Mock()
        mock_git_collector.collect_commits.return_value = [sample_commit_data]
        mock_git_collector_class.return_value = mock_git_collector

        mock_prompt_gen = Mock()
        mock_prompt_gen.generate_prompt.return_value = "Generated prompt"
        mock_prompt_gen.count_approximate_tokens.return_value = 1000
        mock_prompt_gen_class.return_value = mock_prompt_gen

        # Execute main function
        main()

        # Verify initialization calls
        mock_config_class.assert_called_once()
        mock_file_mgr_class.assert_called_once_with(config_loader=mock_config)

        # Verify file management calls
        mock_file_mgr.clear_previous_prompts.assert_called_once()
        mock_file_mgr.move_previous_reports.assert_called_once()
        mock_file_mgr.fetch_report_history.assert_called_once()
        mock_file_mgr.fetch_memo.assert_called_once()
        mock_file_mgr.get_last_report_date.assert_called_once()

        # Verify git data collection (called for each repo)
        assert mock_git_collector_class.call_count == 2
        assert mock_git_collector.collect_commits.call_count == 2

        # Verify prompt generation
        mock_prompt_gen_class.assert_called_once()
        mock_prompt_gen.generate_prompt.assert_called_once()
        mock_prompt_gen.count_approximate_tokens.assert_called_once_with("Generated prompt")

        # Verify file saving
        mock_file_mgr.save_prompt.assert_called_once_with("Generated prompt")
        mock_file_mgr.create_report_file.assert_called_once()

    @patch('weekly_report_prompt.main.Console')
    @patch('weekly_report_prompt.main.ConfigLoader')
    @patch('weekly_report_prompt.main.ReportFileManager')
    @patch('weekly_report_prompt.main.GitDataCollector')
    def test_main_function_no_previous_report(
        self,
        mock_git_collector_class,
        mock_file_mgr_class,
        mock_config_class,
        mock_console_class,
        sample_commit_data
    ):
        """Test main function when no previous report exists."""
        # Setup mocks
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        mock_config = Mock()
        mock_config.get_repositories.return_value = ["/path/to/repo"]
        mock_config_class.return_value = mock_config

        mock_file_mgr = Mock()
        mock_file_mgr.get_last_report_date.return_value = None  # No previous report
        mock_file_mgr.fetch_report_history.return_value = []
        mock_file_mgr.fetch_memo.return_value = None
        mock_file_mgr.prompt_file_path = "/path/to/prompt.md"
        mock_file_mgr_class.return_value = mock_file_mgr

        mock_git_collector = Mock()
        mock_git_collector.collect_commits.return_value = [sample_commit_data]
        mock_git_collector_class.return_value = mock_git_collector

        with patch('weekly_report_prompt.main.PromptGenerator') as mock_prompt_gen_class:
            mock_prompt_gen = Mock()
            mock_prompt_gen.generate_prompt.return_value = "Generated prompt"
            mock_prompt_gen.count_approximate_tokens.return_value = 1000
            mock_prompt_gen_class.return_value = mock_prompt_gen

            with patch('weekly_report_prompt.main.datetime') as mock_datetime:
                mock_now = datetime(2025, 9, 17, 12, 0, 0)
                mock_datetime.now.return_value = mock_now
                # Mock the timedelta calculation
                mock_datetime.return_value = datetime
                expected_date = datetime(2025, 9, 10, 0, 0, 0)

                with patch('weekly_report_prompt.main.timedelta') as mock_timedelta:
                    mock_timedelta.return_value = mock_now - expected_date

                    main()

        # Verify that git collector was called with date from 7 days ago
        expected_date = datetime(2025, 9, 10, 0, 0, 0)
        mock_git_collector.collect_commits.assert_called_with(since_date=expected_date)

    @patch('weekly_report_prompt.main.Console')
    @patch('weekly_report_prompt.main.ConfigLoader')
    @patch('weekly_report_prompt.main.ReportFileManager')
    @patch('weekly_report_prompt.main.GitDataCollector')
    def test_main_function_no_commits_found(
        self,
        mock_git_collector_class,
        mock_file_mgr_class,
        mock_config_class,
        mock_console_class
    ):
        """Test main function when no commits are found."""
        # Setup mocks
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        mock_config = Mock()
        mock_config.get_repositories.return_value = ["/path/to/repo"]
        mock_config_class.return_value = mock_config

        mock_file_mgr = Mock()
        mock_file_mgr.get_last_report_date.return_value = datetime(2025, 9, 10, tzinfo=timezone.utc)
        mock_file_mgr.fetch_report_history.return_value = []
        mock_file_mgr.fetch_memo.return_value = None
        mock_file_mgr_class.return_value = mock_file_mgr

        mock_git_collector = Mock()
        mock_git_collector.collect_commits.return_value = []  # No commits
        mock_git_collector_class.return_value = mock_git_collector

        # Should raise ValueError when no commits found
        with pytest.raises(ValueError, match="No commits found in the specified period"):
            main()

    @patch('weekly_report_prompt.main.Console')
    @patch('weekly_report_prompt.main.ConfigLoader')
    @patch('weekly_report_prompt.main.ReportFileManager')
    @patch('weekly_report_prompt.main.GitDataCollector')
    @patch('weekly_report_prompt.main.PromptGenerator')
    def test_main_function_large_token_count_warning(
        self,
        mock_prompt_gen_class,
        mock_git_collector_class,
        mock_file_mgr_class,
        mock_config_class,
        mock_console_class,
        sample_commit_data
    ):
        """Test main function with large token count warning."""
        # Setup mocks
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        mock_config = Mock()
        mock_config.get_repositories.return_value = ["/path/to/repo"]
        mock_config_class.return_value = mock_config

        mock_file_mgr = Mock()
        mock_file_mgr.get_last_report_date.return_value = datetime(2025, 9, 10, tzinfo=timezone.utc)
        mock_file_mgr.fetch_report_history.return_value = []
        mock_file_mgr.fetch_memo.return_value = None
        mock_file_mgr.prompt_file_path = "/path/to/prompt.md"
        mock_file_mgr_class.return_value = mock_file_mgr

        mock_git_collector = Mock()
        mock_git_collector.collect_commits.return_value = [sample_commit_data]
        mock_git_collector_class.return_value = mock_git_collector

        mock_prompt_gen = Mock()
        mock_prompt_gen.generate_prompt.return_value = "Generated prompt"
        mock_prompt_gen.count_approximate_tokens.return_value = 1500000  # Large token count
        mock_prompt_gen_class.return_value = mock_prompt_gen

        main()

        # Verify warning was printed (check console.print calls)
        warning_calls = [call for call in mock_console.print.call_args_list
                        if len(call[0]) > 0 and "very large" in str(call[0][0])]
        assert len(warning_calls) > 0

    @patch('weekly_report_prompt.main.Console')
    @patch('weekly_report_prompt.main.ConfigLoader')
    @patch('weekly_report_prompt.main.ReportFileManager')
    @patch('weekly_report_prompt.main.GitDataCollector')
    @patch('weekly_report_prompt.main.PromptGenerator')
    def test_main_function_multiple_repositories(
        self,
        mock_prompt_gen_class,
        mock_git_collector_class,
        mock_file_mgr_class,
        mock_config_class,
        mock_console_class,
        sample_commit_data
    ):
        """Test main function with multiple repositories."""
        # Setup mocks
        mock_console = Mock()
        mock_console_class.return_value = mock_console

        mock_config = Mock()
        mock_config.get_repositories.return_value = [
            "/path/to/repo1",
            "/path/to/repo2",
            "/path/to/repo3"
        ]
        mock_config_class.return_value = mock_config

        mock_file_mgr = Mock()
        mock_file_mgr.get_last_report_date.return_value = datetime(2025, 9, 10, tzinfo=timezone.utc)
        mock_file_mgr.fetch_report_history.return_value = []
        mock_file_mgr.fetch_memo.return_value = None
        mock_file_mgr.prompt_file_path = "/path/to/prompt.md"
        mock_file_mgr_class.return_value = mock_file_mgr

        mock_git_collector = Mock()
        mock_git_collector.collect_commits.return_value = [sample_commit_data]
        mock_git_collector_class.return_value = mock_git_collector

        mock_prompt_gen = Mock()
        mock_prompt_gen.generate_prompt.return_value = "Generated prompt"
        mock_prompt_gen.count_approximate_tokens.return_value = 1000
        mock_prompt_gen_class.return_value = mock_prompt_gen

        main()

        # Verify GitDataCollector was created for each repository
        assert mock_git_collector_class.call_count == 3

        # Verify collect_commits was called for each repository
        assert mock_git_collector.collect_commits.call_count == 3

        # Check that project_data was passed with correct structure
        prompt_gen_call_args = mock_prompt_gen_class.call_args
        project_data = prompt_gen_call_args[1]['project_data']
        assert len(project_data) == 3

        # Verify project names are extracted correctly
        expected_names = ["repo1", "repo2", "repo3"]
        actual_names = [project['project_name'] for project in project_data]
        assert actual_names == expected_names

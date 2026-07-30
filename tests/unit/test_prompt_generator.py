from datetime import UTC, datetime

from weekly_report.main import summarize_commit_data
from weekly_report.prompt_generator import PromptGenerator, approximate_tokens, fenced
from weekly_report.schemas import CommitData, CommitStats

TEMPLATE = "# {date}\n\n## Work Done\n* {item}\n"


def make_generator(commits, previous_reports=None, max_diff_lines=25, lang="korean"):
    project_data = [
        {
            "project_name": "Athena",
            "repo_path": "/work/athena",
            "recent_commits": commits,
            "summary": summarize_commit_data(commits),
        }
    ]
    return PromptGenerator(
        project_data=project_data,
        template=TEMPLATE,
        lang=lang,
        max_diff_lines=max_diff_lines,
        previous_reports=previous_reports,
    )


class TestFenced:
    def test_plain_content_gets_three_ticks(self):
        assert fenced("hello", "text") == "```text\nhello\n```"

    def test_fence_outgrows_inner_backtick_runs(self):
        content = "```markdown\ninner fence\n```"
        result = fenced(content)
        assert result.startswith("````\n")
        assert result.endswith("\n````")


class TestApproximateTokens:
    def test_four_chars_per_token(self):
        assert approximate_tokens("x" * 400) == 100


class TestGeneratePrompt:
    def test_contains_template_project_and_language(self, sample_commit_data):
        prompt = make_generator([sample_commit_data]).generate_prompt()

        assert "## 📑 Template" in prompt
        assert TEMPLATE.strip() in prompt
        assert "[Athena]" in prompt
        assert "'korean' language" in prompt
        assert "**Add new feature**" in prompt

    def test_previous_reports_are_fenced_newest_first(self, sample_commit_data):
        prompt = make_generator(
            [sample_commit_data], previous_reports=["# 7/23\n* newest", "# 7/16\n* older"]
        ).generate_prompt()

        assert "## 📜 Previous Weekly Reports" in prompt
        assert prompt.index("* newest") < prompt.index("* older")

    def test_no_memo_section(self, sample_commit_data):
        # The memo mechanism is gone in v0.2; extra context arrives via conversation.
        prompt = make_generator([sample_commit_data]).generate_prompt()
        assert "Memo" not in prompt

    def test_long_diff_is_truncated(self):
        commit = CommitData(
            id="abc123def456",
            author="Test Author",
            email="t@example.com",
            date=datetime(2026, 7, 27, tzinfo=UTC),
            message="big change",
            stats=CommitStats(insertions=100, deletions=0, changed_files=["a.py"]),
            diff="\n".join(f"+line {i}" for i in range(100)),
        )
        prompt = make_generator([commit], max_diff_lines=10).generate_prompt()

        assert "+line 9" in prompt
        assert "+line 10" not in prompt
        assert "showing 10 of 100 total lines" in prompt

    def test_zero_max_diff_lines_omits_diffs(self, sample_commit_data):
        prompt = make_generator([sample_commit_data], max_diff_lines=0).generate_prompt()
        assert "```diff" not in prompt

    def test_empty_commit_list_renders_none(self):
        prompt = make_generator([]).generate_prompt()
        assert "- None" in prompt

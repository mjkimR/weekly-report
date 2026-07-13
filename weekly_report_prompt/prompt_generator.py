import re
from typing import Any

import tiktoken

from weekly_report_prompt.config_loader import ConfigLoader
from weekly_report_prompt.schemas import CommitData

# Used when tiktoken cannot load its encoding; roughly right for English prose and code.
CHARS_PER_TOKEN = 4


def fenced(content: str, info: str = "") -> str:
    """Wrap content in a code fence.

    Reports and templates are markdown and may contain fences of their own, so the
    fence has to be longer than the longest run of backticks inside the content.
    """
    longest_run = max((len(run) for run in re.findall(r"`+", content)), default=0)
    ticks = "`" * max(3, longest_run + 1)
    return f"{ticks}{info}\n{content}\n{ticks}"


class PromptGenerator:
    def __init__(
        self,
        project_data: list[dict[str, Any]],
        config_loader: ConfigLoader,
        previous_reports: list[str] | None = None,
        memo: str | None = None,
    ):
        """
        Args:
            project_data: List of data per project (each dict includes project_name, recent_commits, summary, previous_report, etc.)
            config_loader: Configuration loader instance
        """
        self.project_data = project_data
        self.config_loader = config_loader

        self.max_diff_lines = config_loader.get_max_diff_lines()
        self.lang = config_loader.get_lang()

        # Load template
        self.template = config_loader.get_template()
        self.previous_reports = previous_reports if previous_reports else []
        self.memo = memo

    def _format_commit(self, commit: CommitData, include_diff: bool) -> str:
        """Format a single commit's information as a string."""
        commit_lines = []
        # Commit message (use only the first line, or all lines; here, use all)
        # If the message has multiple lines, emphasize the first line or summarize as needed
        commit_message_lines = commit.message.strip().split("\n")
        formatted_message = f"- **{commit_message_lines[0].strip()}**"  # First line in bold
        if len(commit_message_lines) > 1:
            formatted_message += "\n  " + "\n  ".join(commit_message_lines[1:])

        commit_lines.append(f"{formatted_message} (ID: {commit.id[:7]}, Date: {commit.date.strftime('%Y-%m-%d')})")

        if include_diff and commit.diff:
            diff_content_lines = commit.diff.strip().splitlines()
            if len(diff_content_lines) > self.max_diff_lines:
                diff_display = "\n".join([f"    {line}" for line in diff_content_lines[: self.max_diff_lines]])
                diff_display += f"\n    ... (Some diff lines omitted, showing {self.max_diff_lines} of {len(diff_content_lines)} total lines)"
            else:
                diff_display = "\n".join([f"    {line}" for line in diff_content_lines])

            commit_lines.append(f"  ```diff\n{diff_display}\n  ```")
        return "\n".join(commit_lines)

    def _format_commits(self, commits: list[CommitData], should_include_diff=True) -> str:
        """Format a list of commits as a string."""
        if not commits:
            return "  - None"

        formatted_commits_text = [self._format_commit(commit, include_diff=should_include_diff) for commit in commits]
        return "\n".join(formatted_commits_text)

    def generate_prompt(self, should_include_diff=True) -> str:
        prompt_sections = [
            "# Weekly Work Report Request",
            "Hello! Please draft a weekly work report based on the provided Git activity and previous report (if available).",
        ]

        # --- Template and Previous Report Section ---
        if self.template:
            template_section = [
                "## 📑 Template",
                "Below is the template to use for the report. Please refer to this template to maintain a consistent format.",
                fenced(self.template.strip(), "text"),
            ]
            prompt_sections.append("\n".join(template_section))
        if self.previous_reports:
            # Each report is a whole markdown document, so it gets its own fence rather
            # than being flattened into a list item that mangles its headings and bullets.
            previous_reports_section = [
                "## 📜 Previous Weekly Reports",
                "Below are the contents of previous weekly reports, newest first. Please refer to these to maintain consistency and avoid duplication.",
            ]
            previous_reports_section.extend(fenced(report.strip(), "markdown") for report in self.previous_reports)
            prompt_sections.append("\n\n".join(previous_reports_section))

        if self.memo:
            memo_section = [
                "## 📝 Memo",
                "Below is the memo for this week's report. Please refer to this for additional context or notes.",
                "",
                f"{self.memo}",
            ]
            prompt_sections.append("\n".join(memo_section))

        # --- Per Project Section ---
        for project in self.project_data:
            project_name = project["project_name"]
            summary = project["summary"]
            recent_commits = project["recent_commits"]

            # Summary
            summary_title = f"## 📊 [{project_name}] This Week's Git Activity Summary"
            summary_content = []
            if summary:
                summary_content.append(
                    f"{summary_title} ({summary.start_date.strftime('%Y-%m-%d')} ~ {summary.end_date.strftime('%Y-%m-%d')})"
                )
                summary_content.append(f"- Total commits: {summary.total_commits}")
                summary_content.append(f"- Total lines added: {summary.total_insertions}")
                summary_content.append(f"- Total lines deleted: {summary.total_deletions}")
                summary_content.append(f"- Number of files changed: {summary.total_files_changed}")
            else:
                summary_content.append(summary_title)
                summary_content.append("- No Git activity summary information for this period.")
            prompt_sections.append("\n".join(summary_content))

            # Commit Details
            commit_details_header = f"## 🚀 [{project_name}] Main Progress This Week (Based on Git Commits)"
            commit_details_parts = [
                commit_details_header,
                self._format_commits(recent_commits, should_include_diff),
            ]
            prompt_sections.append("\n".join(commit_details_parts))

        # --- Report Writing Instructions ---
        instructions = [
            "\n## 📄 Report Writing Instructions",
            "\n**Report Style and Notes:**",
            f"- All report content below must be written in '{self.lang}' language.",
            "- Write each item clearly and concisely. Avoid unnecessary repetition or ambiguous expressions.",
            "- Ensure the format matches the template and previous weekly reports, separating titles and content for each item.",
            "- Base the report on commit messages and code changes, and add additional explanations for context if necessary.",
            "- Use a clear, concise, and professional tone that is easy to understand.",
            "- Match the tone and sentence endings to the previous weekly reports provided. If previous reports use concise, note-style bullet points (not full sentences), follow the same style.",
            "- Keep each item brief and in a similar format to the previous reports, using phrases or keywords rather than complete sentences if that is the established style.",
        ]
        prompt_sections.append("\n".join(instructions))

        return "\n\n".join(prompt_sections)

    def count_approximate_tokens(self, text: str, model: str = "gpt-4") -> int:
        """Calculate the approximate number of tokens in the given string.

        tiktoken downloads its encoding on first use. The count is advisory — it only
        drives a warning — so an offline run estimates instead of failing outright.
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            return len(text) // CHARS_PER_TOKEN
        return len(encoding.encode(text))

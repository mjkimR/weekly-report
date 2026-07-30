import re
from typing import Any

from weekly_report.schemas import CommitData

# Roughly right for English prose and code. The count only drives a warning, so a
# heuristic beats carrying a tokenizer dependency for it.
CHARS_PER_TOKEN = 4
TOKEN_ESTIMATE_METHOD = "heuristic"


def approximate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


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
        template: str,
        lang: str,
        max_diff_lines: int,
        previous_reports: list[str] | None = None,
    ):
        """
        Args:
            project_data: List of data per project (each dict includes project_name, recent_commits, summary)
            template: Report template text, shown to the model as the format to follow
            lang: Language the report must be written in, inserted verbatim
            max_diff_lines: Per-commit diff line budget; 0 omits diffs entirely
            previous_reports: Past report contents, newest first
        """
        self.project_data = project_data
        self.template = template
        self.lang = lang
        self.max_diff_lines = max_diff_lines
        self.previous_reports = previous_reports if previous_reports else []

    def _format_commit(self, commit: CommitData, include_diff: bool) -> str:
        """Format a single commit's information as a string."""
        commit_lines = []
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
        # max_diff_lines == 0 means "commit messages only".
        should_include_diff = should_include_diff and self.max_diff_lines > 0

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

import os
import re
from datetime import datetime
from pathlib import Path

from weekly_report_prompt.config_loader import ConfigLoader
from weekly_report_prompt.const import MEMO_BLANK_MESSAGE, REPORT_BLANK_MESSAGE

REPORT_FILENAME_RE = re.compile(r"^report-(\d{8}-\d{6})\.md$")


def report_date(path):
    """Return the date encoded in a report filename, or None if it is not a report."""
    match = REPORT_FILENAME_RE.match(os.path.basename(path))
    if match is None:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")


class ReportFileManager:
    def __init__(self, config_loader: ConfigLoader, build_dir=None):
        if build_dir is None:
            build_dir = os.path.join(Path(__file__).parent.parent, "build")
            os.makedirs(build_dir, exist_ok=True)
        if not os.path.isdir(build_dir):
            raise NotADirectoryError(f"Build directory does not exist: {build_dir}")
        self.build_dir = build_dir
        self.history_dir = os.path.join(self.build_dir, "history")
        os.makedirs(self.history_dir, exist_ok=True)

        self.history_limit = config_loader.get_report_history_limit()
        self.prompt_file_path = None

    def get_today_str(self):
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def save_prompt(self, prompt_text):
        filename = f"prompt-{self.get_today_str()}.md"
        path = os.path.join(self.build_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(prompt_text)
        self.prompt_file_path = path
        return path

    def create_report_file(self):
        filename = f"report-{self.get_today_str()}.md"
        path = os.path.join(self.build_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(REPORT_BLANK_MESSAGE)
        return path

    def previous_prompt_files(self):
        """Prompt files from earlier runs, which the next run replaces."""
        return sorted(
            os.path.join(self.build_dir, filename)
            for filename in os.listdir(self.build_dir)
            if filename.startswith("prompt-") and filename.endswith(".md")
        )

    def pending_report_files(self):
        """Reports still sitting in the build directory, awaiting archival."""
        return sorted(
            os.path.join(self.build_dir, filename)
            for filename in os.listdir(self.build_dir)
            if report_date(filename) is not None
        )

    def move_previous_reports(self):
        """Archive reports the user filled in; discard the ones left blank."""
        for file_path in self.pending_report_files():
            if self._is_blank_report(file_path):
                os.remove(file_path)
            else:
                dest_path = os.path.join(self.history_dir, os.path.basename(file_path))
                os.rename(file_path, dest_path)

        # Clean up old history files if they exceed the limit
        self._cleanup_old_history_files()

    @staticmethod
    def _is_blank_report(file_path):
        with open(file_path, encoding="utf-8") as f:
            return f.read().strip() == REPORT_BLANK_MESSAGE.strip()

    @staticmethod
    def _entries(paths):
        """Pair each report path with the date in its filename, newest first.

        Paths that are not reports are dropped, so callers never have to filter first.
        """
        entries = [(date, path) for path in paths if (date := report_date(path)) is not None]
        entries.sort(key=lambda entry: entry[0], reverse=True)
        return entries

    def _history_entries(self):
        """Return (date, path) for every archived report, newest first."""
        return self._entries(os.path.join(self.history_dir, filename) for filename in os.listdir(self.history_dir))

    def _report_entries(self):
        """Every report we know of, archived or not, newest first.

        A report still in the build directory counts as soon as it has been filled in:
        it marks a period already reported on, so callers must not have to archive it
        first in order to see it. A blank one was never written, so it does not count.
        """
        pending = self._entries(path for path in self.pending_report_files() if not self._is_blank_report(path))
        entries = self._history_entries() + pending
        entries.sort(key=lambda entry: entry[0], reverse=True)
        return entries

    def _cleanup_old_history_files(self):
        """Remove old history files that exceed the history limit."""
        for _, file_path in self._history_entries()[self.history_limit :]:
            os.remove(file_path)

    def fetch_report_history(self):
        """Return the contents of the most recent reports, newest first."""
        reports = []
        for _, file_path in self._report_entries()[: self.history_limit]:
            with open(file_path, encoding="utf-8") as f:
                reports.append(f.read())

        return reports

    def get_last_report_date(self):
        """Return the date of the last report."""
        entries = self._report_entries()
        return entries[0][0] if entries else None

    def clear_previous_prompts(self):
        """Clear all previous prompt files."""
        for file_path in self.previous_prompt_files():
            os.remove(file_path)

    def fetch_memo(self):
        """Return the memo contents, or None if it is absent or still blank."""
        memo_path = os.path.join(self.build_dir, "memo.md")
        if not os.path.exists(memo_path):
            return None

        with open(memo_path, encoding="utf-8") as f:
            memo = f.read().strip()

        if memo == MEMO_BLANK_MESSAGE.strip():
            return None
        return memo

    def ensure_memo_file(self):
        """Recreate the memo placeholder if it is missing."""
        memo_path = os.path.join(self.build_dir, "memo.md")
        if not os.path.exists(memo_path):
            with open(memo_path, "w", encoding="utf-8") as f:
                f.write(MEMO_BLANK_MESSAGE)
        return memo_path

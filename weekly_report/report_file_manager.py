"""report.md, prompt.md and history/ under the home directory.

history/ is the only state this tool carries between runs: the newest report date
decides the next collection window, so everything here errs on the side of not losing
or misdating a report.

report.md has a fixed name, so unlike the archived files its creation time is not in
the filename. That time is the end of the period the report covers, and it is recorded
as a markdown comment on the first line; if the line disappears (the file was rewritten
from scratch), the file's modification time is the fallback, which can silently push
the window past commits made between the run and the last edit.
"""

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from weekly_report.paths import Home

REPORT_FILENAME_RE = re.compile(r"^report-(\d{8}-\d{6})\.md$")
REPORT_FILENAME_FORMAT = "%Y%m%d-%H%M%S"

CREATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%S"

_CREATED_MARKER_RE = re.compile(r"\[//\]: # \(weekly-report: created (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\)")
_COMMENT_LINE_RE = re.compile(r"^\[//\]: # \(.*\)\s*$")

REPORT_BLANK_MESSAGE = "[//]: # (Write this week's report here. Keep the 'created' line above as-is: it marks where the next collection window starts.)"


def report_date(filename: str) -> datetime | None:
    """Return the date encoded in a report filename, or None if it is not a report."""
    match = REPORT_FILENAME_RE.match(filename)
    if match is None:
        return None
    return datetime.strptime(match.group(1), REPORT_FILENAME_FORMAT)


def blank_report_content(created: datetime) -> str:
    return f"[//]: # (weekly-report: created {created.strftime(CREATED_AT_FORMAT)})\n{REPORT_BLANK_MESSAGE}\n"


def parse_created_marker(text: str) -> datetime | None:
    match = _CREATED_MARKER_RE.search(text)
    if match is None:
        return None
    return datetime.strptime(match.group(1), CREATED_AT_FORMAT)


def is_blank_report_text(text: str) -> bool:
    """A report is blank while nothing but markdown comments is in it.

    Comparing against the exact placeholder would flip to "filled" the moment the user
    deletes a placeholder line without writing anything.
    """
    without_comments = "\n".join(line for line in text.splitlines() if not _COMMENT_LINE_RE.match(line))
    return without_comments.strip() == ""


def strip_report_marks(text: str) -> str:
    """Drop the created marker and placeholder lines before embedding a report elsewhere.

    They are our bookkeeping, not report content; left in, the model sees them in every
    past report and may imitate them.
    """
    lines = [
        line
        for line in text.splitlines()
        if not _CREATED_MARKER_RE.search(line) and line.rstrip() != REPORT_BLANK_MESSAGE
    ]
    return "\n".join(lines).lstrip("\n")


def import_report(home: Home, source: Path, date: datetime) -> Path:
    """Copy an existing report into history/ under the given date."""
    home.ensure()
    destination = home.history_dir / f"report-{date.strftime(REPORT_FILENAME_FORMAT)}.md"
    if destination.exists():
        raise FileExistsError(f"already in history: {destination}")
    shutil.copyfile(source, destination)
    return destination


class ReportFileManager:
    def __init__(self, home: Home, history_limit: int):
        self.home = home
        self.history_limit = history_limit

    # --- history/ ---

    def history_entries(self) -> list[tuple[datetime, Path]]:
        """(date, path) for every archived report, newest first. Non-reports are ignored."""
        if not self.home.history_dir.is_dir():
            return []
        entries = [(date, path) for path in self.home.history_dir.iterdir() if (date := report_date(path.name))]
        entries.sort(key=lambda entry: entry[0], reverse=True)
        return entries

    def trim_history(self) -> None:
        """Delete the oldest archived reports beyond the history limit."""
        for _, path in self.history_entries()[self.history_limit :]:
            path.unlink()

    # --- report.md ---

    def report_md_is_filled(self) -> bool:
        path = self.home.report_path
        if not path.exists():
            return False
        return not is_blank_report_text(path.read_text(encoding="utf-8"))

    def report_md_date(self) -> tuple[datetime, bool]:
        """When the current report.md's period ended, and whether mtime was the source.

        The created marker records when `run` produced the file; commits made after that
        belong to the next report even if the user edits this one days later. Only when
        the marker was erased does mtime stand in.
        """
        path = self.home.report_path
        created = parse_created_marker(path.read_text(encoding="utf-8"))
        if created is not None:
            return created, False
        return datetime.fromtimestamp(path.stat().st_mtime).replace(microsecond=0), True

    def known_reports(self) -> list[tuple[datetime, Path]]:
        """Archived reports plus a filled report.md, newest first.

        A filled report.md marks a period already reported on before it is archived, so
        the collection window must see it. A blank one was never written and does not
        count.
        """
        entries = self.history_entries()
        if self.report_md_is_filled():
            date, _ = self.report_md_date()
            entries.append((date, self.home.report_path))
            entries.sort(key=lambda entry: entry[0], reverse=True)
        return entries

    def last_report_date(self) -> datetime | None:
        entries = self.known_reports()
        return entries[0][0] if entries else None

    def fetch_report_history(self) -> list[str]:
        """Contents of the most recent reports for the prompt, newest first, up to the limit."""
        return [
            strip_report_marks(path.read_text(encoding="utf-8"))
            for _, path in self.known_reports()[: self.history_limit]
        ]

    def archive_report_md(self) -> Path | None:
        """Move a filled report.md into history/; discard a blank one."""
        path = self.home.report_path
        if not path.exists():
            return None
        if not self.report_md_is_filled():
            path.unlink()
            return None

        date, _ = self.report_md_date()
        self.home.ensure()
        destination = self.home.history_dir / f"report-{date.strftime(REPORT_FILENAME_FORMAT)}.md"
        # A same-second collision should not overwrite an existing report.
        while destination.exists():
            date += timedelta(seconds=1)
            destination = self.home.history_dir / f"report-{date.strftime(REPORT_FILENAME_FORMAT)}.md"
        shutil.move(path, destination)
        return destination

    # --- write phase ---

    def write_prompt(self, text: str) -> Path:
        self.home.ensure()
        self.home.prompt_path.write_text(text, encoding="utf-8")
        return self.home.prompt_path

    def create_blank_report(self, created: datetime) -> Path:
        self.home.ensure()
        self.home.report_path.write_text(blank_report_content(created), encoding="utf-8")
        return self.home.report_path

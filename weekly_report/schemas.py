from datetime import datetime
from pathlib import PurePath

from pydantic import BaseModel, Field, model_validator


class RepositoryEntry(BaseModel):
    """One repository the report covers."""

    path: str
    # Shown verbatim in report headings. The last path segment is usually a lowercase
    # directory name, which reads poorly there, so it is only the fallback.
    name: str | None = None
    # Commit author names differ between repositories more often than expected. When
    # unset, the global `author` is the only match, and a mismatch shows up as a silent
    # zero -- `repo add` warns about that at registration time.
    authors: list[str] | None = None

    def display_name(self) -> str:
        return self.name or PurePath(self.path.rstrip("/")).name

    def effective_authors(self, global_author: str | None) -> list[str]:
        if self.authors:
            return self.authors
        return [global_author] if global_author else []


class AppConfig(BaseModel):
    """Validated contents of ~/.weekly-report/config.yaml."""

    # Global default author; repository[].authors overrides it per repository. Optional
    # only because every repository may carry its own list -- the validator below rejects
    # a repository that ends up with no authors at all.
    author: str | None = None
    # Inserted verbatim into the prompt as the language the report must be written in.
    lang: str = "english"
    repository: list[RepositoryEntry] = Field(default_factory=list)
    # Zero is coherent -- commit messages, no diffs. A negative value would reach
    # `lines[:n]` and quietly drop the tail of every diff instead.
    max_diff_lines: int = Field(default=50, ge=0)
    # This also slices history/ for deletion, so zero would empty the archive. That
    # archive is the only record of which periods have already been reported on, it
    # decides the next run's collection window, and Git does not track it.
    report_history_limit: int = Field(default=5, ge=1)
    # Advisory only, and nothing enforces it. How many tokens are too many depends on the
    # agent's model, so this is a setting rather than a constant. The default leaves
    # headroom under a ~200k context window, on the theory that a prompt this large is
    # mostly diff noise anyway.
    large_prompt_tokens: int = Field(default=150_000, gt=0)

    @model_validator(mode="after")
    def _every_repository_has_an_author(self):
        for entry in self.repository:
            if not entry.effective_authors(self.author):
                raise ValueError(f"repository '{entry.display_name()}' has no authors and no global author is set")
        return self


class CommitStats(BaseModel):
    insertions: int
    deletions: int
    changed_files: list[str]


class CommitData(BaseModel):
    id: str
    author: str
    email: str
    date: datetime
    message: str
    stats: CommitStats
    diff: str

    @classmethod
    def from_commit(cls, commit, diff):
        """Create a CommitData instance from a commit object."""
        return cls(
            id=commit.hexsha,
            author=commit.author.name,
            email=commit.author.email,
            date=commit.committed_datetime,
            message=commit.message.strip(),
            stats=CommitStats(
                insertions=commit.stats.total["insertions"],
                deletions=commit.stats.total["deletions"],
                changed_files=sorted(commit.stats.files),
            ),
            diff=diff,
        )


class CommitDataSummary(BaseModel):
    start_date: datetime
    end_date: datetime

    total_commits: int
    total_insertions: int
    total_deletions: int
    total_files_changed: int

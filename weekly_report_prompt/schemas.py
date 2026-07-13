from datetime import datetime

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Validated contents of config/config.yaml."""

    author: str
    repository: list[str] = Field(default_factory=list)
    # Zero is coherent -- commit messages, no diffs. A negative value would reach
    # `lines[:n]` and quietly drop the tail of every diff instead.
    max_diff_lines: int = Field(default=25, ge=0)
    lang: str = "ko"
    # This also slices build/history for deletion, so zero would empty the archive. That
    # archive is the only record of which periods have already been reported on, it decides
    # the next run's collection window, and Git does not track it.
    report_history_limit: int = Field(default=10, ge=1)
    # Advisory only, and nothing enforces it. How many tokens are too many depends on the
    # model you paste the prompt into -- Claude fits ~200k, Gemini and GPT ~1M -- so this
    # is a setting rather than a constant. The default leaves headroom under the smallest
    # of those, on the theory that a prompt this large is mostly diff noise anyway.
    large_prompt_tokens: int = Field(default=150_000, gt=0)


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
            date=commit.committed_datetime.isoformat(),
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

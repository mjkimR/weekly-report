import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from weekly_report.paths import Home
from weekly_report.schemas import CommitData, CommitStats


@pytest.fixture
def home(tmp_path, monkeypatch) -> Home:
    """A Home under tmp_path, also exported so CLI invocations in tests use it."""
    root = tmp_path / "wr-home"
    monkeypatch.setenv("WEEKLY_REPORT_HOME", str(root))
    return Home(root)


def _git(repo_path: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(repo_path), **(env or {})},
    )


@pytest.fixture
def make_repo(tmp_path):
    """Create a real git repository under tmp_path."""

    def _make(name: str = "repo", user_name: str = "Test Author", email: str = "test@example.com") -> Path:
        path = tmp_path / name
        path.mkdir(parents=True)
        _git(path, "init", "-q")
        _git(path, "config", "user.name", user_name)
        _git(path, "config", "user.email", email)
        return path

    return _make


@pytest.fixture
def commit_in():
    """Add a commit to a repository, optionally as a different author or date."""

    def _commit(
        repo_path: Path,
        message: str = "feat: change",
        filename: str = "f.txt",
        author: str | None = None,
        email: str | None = None,
        date: str | None = None,
    ) -> None:
        target = repo_path / filename
        with target.open("a", encoding="utf-8") as f:
            f.write(f"{message}\n")
        env = {}
        if author:
            env["GIT_AUTHOR_NAME"] = author
            env["GIT_COMMITTER_NAME"] = author
        if email:
            env["GIT_AUTHOR_EMAIL"] = email
            env["GIT_COMMITTER_EMAIL"] = email
        if date:
            env["GIT_AUTHOR_DATE"] = date
            env["GIT_COMMITTER_DATE"] = date
        _git(repo_path, "add", "-A", env=env)
        _git(repo_path, "commit", "-q", "-m", message, env=env)

    return _commit


@pytest.fixture
def sample_commit_data():
    return CommitData(
        id="abc123def456",
        author="Test Author",
        email="test@example.com",
        date=datetime(2026, 7, 27, 10, 30, 0, tzinfo=UTC),
        message="Add new feature\n\nDetailed description of the feature",
        stats=CommitStats(insertions=15, deletions=5, changed_files=["a.py", "b.py", "c.py"]),
        diff="@@ -1,3 +1,3 @@\n-old line\n+new line",
    )

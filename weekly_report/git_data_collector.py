import os
from datetime import datetime

import git

from weekly_report.schemas import CommitData


def open_repository(path: str) -> git.Repo:
    """Open the repository containing `path`, walking up to the root if needed.

    Raises git.InvalidGitRepositoryError or git.NoSuchPathError, which callers map to
    exit code 3.
    """
    return git.Repo(path, search_parent_directories=True)


class GitDataCollector:
    def __init__(self, repo_path: str, authors: list[str]):
        self.authors = set(authors)
        self.repo = open_repository(repo_path)
        self._empty_tree_sha = None

    def collect_commits(self, since_date: datetime) -> list[CommitData]:
        """Collect commits since the given date, excluding merges and other authors."""
        commits = []
        for commit in _iter_commits(self.repo, since_date):
            if commit.author.name not in self.authors:
                continue
            commits.append(CommitData.from_commit(commit, self.get_commit_diff(commit.hexsha)))
        return commits

    def _get_empty_tree_sha(self) -> str:
        """Return this repo's empty tree hash, the diff base for an initial commit."""
        if self._empty_tree_sha is None:
            self._empty_tree_sha = self.repo.git.hash_object("-t", "tree", os.devnull)
        return self._empty_tree_sha

    def get_commit_diff(self, commit_id: str) -> str:
        """Return the diff information for a specific commit."""
        commit = self.repo.commit(commit_id)
        if len(commit.parents) > 0:
            return self.repo.git.diff(commit.parents[0], commit)
        else:
            return self.repo.git.diff(self._get_empty_tree_sha(), commit)


def _iter_commits(repo: git.Repo, since: datetime):
    """Walk every branch, local and remote, skipping merge commits.

    Not `all=True`: that also walks refs/stash, which would report stashed
    work-in-progress as completed work. A repository whose HEAD is unborn raises
    ValueError; either way, no refs means "no commits".
    """
    try:
        for commit in repo.iter_commits(branches=True, remotes=True, since=since):
            if len(commit.parents) > 1:
                continue
            yield commit
    except (git.GitCommandError, ValueError):
        return


def author_candidates(repo: git.Repo, since: datetime) -> list[dict]:
    """Commit author candidates with commit counts, most active first."""
    counts: dict[tuple[str, str], int] = {}
    for commit in _iter_commits(repo, since):
        key = (str(commit.author.name), str(commit.author.email))
        counts[key] = counts.get(key, 0) + 1
    candidates = [{"name": name, "email": email, "commits": count} for (name, email), count in counts.items()]
    candidates.sort(key=lambda candidate: (-candidate["commits"], candidate["name"]))
    return candidates


def configured_user_name(repo: git.Repo) -> str | None:
    """The repo's effective `git config user.name`, which may differ from commit authors."""
    with repo.config_reader() as reader:
        # Not default=None: GitPython re-raises on a missing key when the default is
        # None, and a machine with no git identity at all must not crash `authors`.
        value = reader.get_value("user", "name", default="")
    return str(value) if value else None


def has_commits_by(repo: git.Repo, authors: list[str], since: datetime) -> bool:
    author_set = set(authors)
    return any(commit.author.name in author_set for commit in _iter_commits(repo, since))

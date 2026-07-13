"""Integration tests that exercise GitDataCollector against a real git repository.

The unit tests mock `repo.git`, so they can only prove the collector calls git the way
we expect it to. These tests prove git actually accepts what we hand it, and that the
set of commits we walk is the set we meant to walk.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from git import Actor, Repo

from weekly_report_prompt.git_data_collector import GitDataCollector

pytestmark = pytest.mark.integration

AUTHOR = Actor("Test Author", "test@example.com")
OTHER_AUTHOR = Actor("Other Author", "other@example.com")

SINCE = datetime.now() - timedelta(days=1)


@pytest.fixture
def repo(tmp_path):
    """A real, throwaway git repository owned by the configured test author."""
    repo = Repo.init(tmp_path / "repo")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", AUTHOR.name)
        cw.set_value("user", "email", AUTHOR.email)
    return repo


def commit_file(repo, name, content, message, author=AUTHOR):
    """Write a file, stage it, and commit it."""
    Path(repo.working_tree_dir, name).write_text(content, encoding="utf-8")
    repo.index.add([name])
    return repo.index.commit(message, author=author, committer=AUTHOR)


def collect_messages(repo, config_loader):
    collector = GitDataCollector(config_loader, repo.working_tree_dir)
    return [commit.message for commit in collector.collect_commits(SINCE)]


def test_initial_commit_diff_is_produced(repo, config_loader):
    """An initial commit has no parent, so it is diffed against the empty tree."""
    commit = commit_file(repo, "a.txt", "hello\n", "feat: initial commit")

    collector = GitDataCollector(config_loader, repo.working_tree_dir)
    diff = collector.get_commit_diff(commit.hexsha)

    assert "a.txt" in diff
    assert "+hello" in diff


def test_initial_commit_is_collected(repo, config_loader):
    """The whole collect path works on a repo whose first commit is in range."""
    commit_file(repo, "a.txt", "hello\n", "feat: initial commit")

    collector = GitDataCollector(config_loader, repo.working_tree_dir)
    commits = collector.collect_commits(SINCE)

    assert [c.message for c in commits] == ["feat: initial commit"]
    assert "+hello" in commits[0].diff


def test_stashed_work_is_not_collected(repo, config_loader):
    """`git stash` writes commits under refs/stash; they are not completed work."""
    commit_file(repo, "a.txt", "one\n", "feat: real work")

    Path(repo.working_tree_dir, "a.txt").write_text("two\n", encoding="utf-8")
    repo.git.stash("push", "-m", "half-finished experiment")

    # Guard the premise: the stash really did create commits authored by us.
    stashed = list(repo.iter_commits("refs/stash"))
    assert stashed and stashed[0].author.name == AUTHOR.name

    assert collect_messages(repo, config_loader) == ["feat: real work"]


def test_commits_on_other_branches_are_collected(repo, config_loader):
    """Work on a branch that is not checked out still belongs in the report."""
    commit_file(repo, "a.txt", "one\n", "feat: on the default branch")

    repo.git.checkout("-b", "feature")
    commit_file(repo, "b.txt", "two\n", "feat: on a feature branch")
    repo.git.checkout("-")

    assert set(collect_messages(repo, config_loader)) == {
        "feat: on the default branch",
        "feat: on a feature branch",
    }


def test_merge_commits_and_other_authors_are_excluded(repo, config_loader):
    """Only non-merge commits written by the configured author are collected."""
    commit_file(repo, "a.txt", "base\n", "feat: mine")

    repo.git.checkout("-b", "side")
    commit_file(repo, "b.txt", "side\n", "feat: someone else's", author=OTHER_AUTHOR)
    repo.git.checkout("-")
    repo.git.merge("side", "--no-ff", "-m", "merge: side into default")

    assert collect_messages(repo, config_loader) == ["feat: mine"]


def test_commits_before_the_cutoff_are_excluded(repo, config_loader):
    """`since_date` bounds the walk."""
    commit_file(repo, "a.txt", "old\n", "feat: last month")

    collector = GitDataCollector(config_loader, repo.working_tree_dir)
    commits = collector.collect_commits(datetime.now() + timedelta(days=1))

    assert commits == []

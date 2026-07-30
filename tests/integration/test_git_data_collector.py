from datetime import datetime, timedelta

import git
import pytest

from weekly_report.git_data_collector import (
    GitDataCollector,
    author_candidates,
    configured_user_name,
    has_commits_by,
    open_repository,
)

pytestmark = pytest.mark.integration

A_WEEK_AGO = datetime.now() - timedelta(days=7)


class TestOpenRepository:
    def test_finds_root_from_subdirectory(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path)
        sub = repo_path / "src" / "deep"
        sub.mkdir(parents=True)

        repo = open_repository(str(sub))
        assert repo.working_tree_dir == str(repo_path)

    def test_rejects_a_plain_directory(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(git.InvalidGitRepositoryError):
            open_repository(str(plain))

    def test_rejects_a_missing_path(self, tmp_path):
        with pytest.raises(git.NoSuchPathError):
            open_repository(str(tmp_path / "nope"))


class TestCollectCommits:
    def test_matches_any_of_the_given_authors(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path, message="mine", author="minjae.kim", email="m@example.com")
        commit_in(repo_path, message="also mine", author="mjkim", email="m@example.com")
        commit_in(repo_path, message="not mine", author="someone.else", email="s@example.com")

        collector = GitDataCollector(str(repo_path), authors=["minjae.kim", "mjkim"])
        messages = {commit.message for commit in collector.collect_commits(A_WEEK_AGO)}
        assert messages == {"mine", "also mine"}

    def test_since_excludes_old_commits(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path, message="ancient", date="2020-01-01T09:00:00")
        commit_in(repo_path, message="recent")

        collector = GitDataCollector(str(repo_path), authors=["Test Author"])
        messages = [commit.message for commit in collector.collect_commits(A_WEEK_AGO)]
        assert messages == ["recent"]

    def test_diff_is_attached(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: add line")

        (commit,) = GitDataCollector(str(repo_path), authors=["Test Author"]).collect_commits(A_WEEK_AGO)
        assert "feat: add line" in commit.diff

    def test_empty_repository_collects_nothing(self, make_repo):
        repo_path = make_repo()
        collector = GitDataCollector(str(repo_path), authors=["Test Author"])
        assert collector.collect_commits(A_WEEK_AGO) == []


class TestAuthorHelpers:
    def test_candidates_counted_and_sorted(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path, author="busy", email="b@example.com")
        commit_in(repo_path, author="busy", email="b@example.com")
        commit_in(repo_path, author="quiet", email="q@example.com")

        repo = open_repository(str(repo_path))
        candidates = author_candidates(repo, A_WEEK_AGO)
        assert candidates == [
            {"name": "busy", "email": "b@example.com", "commits": 2},
            {"name": "quiet", "email": "q@example.com", "commits": 1},
        ]

    def test_configured_user_name(self, make_repo):
        repo = open_repository(str(make_repo(user_name="Configured Name")))
        assert configured_user_name(repo) == "Configured Name"

    def test_configured_user_name_missing_everywhere(self, tmp_path, monkeypatch):
        # A fresh machine may have no git identity at any config level; `authors`
        # must report None instead of crashing.
        monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-xdg"))
        repo = git.Repo.init(tmp_path / "no-identity")
        assert configured_user_name(repo) is None

    def test_has_commits_by(self, make_repo, commit_in):
        repo_path = make_repo()
        commit_in(repo_path, author="minjae.kim", email="m@example.com")
        repo = open_repository(str(repo_path))

        assert has_commits_by(repo, ["minjae.kim"], A_WEEK_AGO)
        assert not has_commits_by(repo, ["someone.else"], A_WEEK_AGO)

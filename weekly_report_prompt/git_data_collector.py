import os
from datetime import datetime

import git

from weekly_report_prompt.config_loader import ConfigLoader
from weekly_report_prompt.schemas import CommitData


class GitDataCollector:
    def __init__(self, config_loader: ConfigLoader, repo_path: str = "."):
        self.config_loader = config_loader
        self.author = config_loader.get_author()
        self.repo = git.Repo(repo_path)
        self._empty_tree_sha = None

    def collect_commits(
        self,
        since_date: datetime,
    ) -> list[CommitData]:
        """Collect commits since the given date, excluding merge commits and those not matching the configured author."""
        commits = []
        # Walk every branch, local and remote, so work done outside the checked-out
        # branch is reported. Not `all=True`: that also walks refs/stash, which would
        # report stashed work-in-progress as completed work.
        for commit in self.repo.iter_commits(branches=True, remotes=True, since=since_date):
            # Exclude merge commits
            if len(commit.parents) > 1:
                continue
            # Exclude commits not matching the author
            if commit.author.name != self.author:
                continue

            commit_data = CommitData.from_commit(commit, self.get_commit_diff(commit.hexsha))
            commits.append(commit_data)

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

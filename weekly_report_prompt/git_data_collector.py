import git
from datetime import datetime
from typing import List

from weekly_report_prompt.schemas import CommitData
from weekly_report_prompt.config_loader import ConfigLoader


class GitDataCollector:
    def __init__(self, config_loader: ConfigLoader, repo_path: str = "."):
        self.config_loader = config_loader
        self.author = config_loader.get_author()
        self.repo = git.Repo(repo_path)

    def collect_commits(
        self,
        since_date: datetime,
    ) -> List[CommitData]:
        """Collect commits since the given date, excluding merge commits and those not matching the configured author."""
        commits = []
        for commit in self.repo.iter_commits(all=True, since=since_date):
            # Exclude merge commits
            if len(commit.parents) > 1:
                continue
            # Exclude commits not matching the author
            if commit.author.name != self.author:
                continue

            commit_data = CommitData.from_commit(
                commit, self.get_commit_diff(commit.hexsha)
            )
            commits.append(commit_data)

        return commits

    def get_commit_diff(self, commit_id: str) -> str:
        """Return the diff information for a specific commit."""
        commit = self.repo.commit(commit_id)
        if len(commit.parents) > 0:
            return self.repo.git.diff(commit.parents[0], commit)
        else:
            return self.repo.git.diff(git.NULL_TREE, commit)

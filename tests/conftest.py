import pytest
import tempfile
import os
from datetime import datetime, timezone
from unittest.mock import Mock
import yaml

from weekly_report_prompt.config_loader import ConfigLoader
from weekly_report_prompt.schemas import CommitData, CommitStats


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def sample_config():
    """Provide sample configuration data."""
    return {
        "author": "Test Author",
        "repository": ["/path/to/repo"],
        "max_diff_lines": 25,
        "lang": "ko",
        "report_history_limit": 10
    }


@pytest.fixture
def config_file(temp_dir, sample_config):
    """Create a temporary config file."""
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)

    config_path = os.path.join(config_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(sample_config, f)

    return config_path


@pytest.fixture
def template_file(temp_dir):
    """Create a temporary template file."""
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)

    template_path = os.path.join(config_dir, "template.md")
    template_content = """# Weekly Report Template

## Project: {project_name}

### Summary
{summary}

### Recent Commits
{recent_commits}
"""
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(template_content)

    return template_path


@pytest.fixture
def config_loader(config_file, template_file):
    """Provide a ConfigLoader instance with test files."""
    return ConfigLoader(config_path=config_file, template_path=template_file)


@pytest.fixture
def sample_commit_data():
    """Provide sample commit data for testing."""
    return CommitData(
        id="abc123def456",
        author="Test Author",
        email="test@example.com",
        date=datetime(2025, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
        message="Add new feature\n\nDetailed description of the feature",
        stats=CommitStats(
            insertions=15,
            deletions=5,
            changed_files=["a.py", "b.py", "c.py"]
        ),
        diff="@@ -1,3 +1,3 @@\n-old line\n+new line"
    )


@pytest.fixture
def mock_git_repo():
    """Provide a mock Git repository."""
    mock_repo = Mock()

    # Mock commit object
    mock_commit = Mock()
    mock_commit.hexsha = "abc123def456"
    mock_commit.author.name = "Test Author"
    mock_commit.author.email = "test@example.com"
    mock_commit.committed_datetime = datetime(2025, 9, 15, 10, 30, 0, tzinfo=timezone.utc)
    mock_commit.message = "Add new feature\n\nDetailed description"
    mock_commit.parents = []
    mock_commit.stats.total = {
        "insertions": 15,
        "deletions": 5,
        "files": 3
    }
    mock_commit.stats.files = {"a.py": {}, "b.py": {}, "c.py": {}}

    mock_repo.iter_commits.return_value = [mock_commit]
    mock_repo.commit.return_value = mock_commit
    mock_repo.git.diff.return_value = "@@ -1,3 +1,3 @@\n-old line\n+new line"

    return mock_repo


@pytest.fixture
def build_dir(temp_dir):
    """Provide a temporary build directory."""
    build_path = os.path.join(temp_dir, "build")
    os.makedirs(build_path, exist_ok=True)
    return build_path

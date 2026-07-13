"""End-to-end tests for the CLI, driving main() against a real repo and build directory.

These exist because the interesting failures are side effects: main() used to clear the
previous prompt and archive the previous report *before* it knew whether there were any
commits to report on, so a run that failed still destroyed state. Only a test that looks
at the filesystem can catch that.
"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from git import Actor, Repo

from weekly_report_prompt.const import REPORT_BLANK_MESSAGE
from weekly_report_prompt.main import main
from weekly_report_prompt.prompt_generator import PromptGenerator

pytestmark = pytest.mark.integration

AUTHOR = Actor("Test Author", "test@example.com")
OTHER_AUTHOR = Actor("Other Author", "other@example.com")

STALE_PROMPT = "prompt-20250101-000000.md"
FILLED_REPORT = "report-20250917-120000.md"
FILLED_REPORT_BODY = "# last week\n\n* shipped the thing"


@pytest.fixture(autouse=True)
def offline_token_count(monkeypatch):
    """tiktoken downloads its encoding on first use; these tests are about files."""
    monkeypatch.setattr(
        PromptGenerator,
        "count_approximate_tokens",
        lambda self, text, model="gpt-4": len(text) // 4,
    )


@pytest.fixture
def repo(tmp_path):
    repo = Repo.init(tmp_path / "my-project")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", AUTHOR.name)
        cw.set_value("user", "email", AUTHOR.email)
    return repo


def commit_file(repo, name, content, message, author=AUTHOR):
    Path(repo.working_tree_dir, name).write_text(content, encoding="utf-8")
    repo.index.add([name])
    return repo.index.commit(message, author=author, committer=AUTHOR)


@pytest.fixture
def workspace(tmp_path, repo):
    """A build directory holding a stale prompt and a report the user has filled in."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "author": AUTHOR.name,
                "repository": [repo.working_tree_dir],
                "lang": "ko",
                "max_diff_lines": 5,
                "report_history_limit": 5,
            }
        ),
        encoding="utf-8",
    )

    template_path = tmp_path / "template.md"
    template_path.write_text("# {date}\n\n## Work Done\n", encoding="utf-8")

    build_dir = tmp_path / "build"
    (build_dir / "history").mkdir(parents=True)
    (build_dir / STALE_PROMPT).write_text("an old prompt", encoding="utf-8")
    (build_dir / FILLED_REPORT).write_text(FILLED_REPORT_BODY, encoding="utf-8")

    return {
        "argv": [
            "--config",
            str(config_path),
            "--template",
            str(template_path),
            "--build-dir",
            str(build_dir),
        ],
        "build_dir": build_dir,
    }


def snapshot(root):
    """Every file under root, mapped to its contents."""
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(Path(root).rglob("*"))
        if path.is_file()
    }


def test_dry_run_writes_nothing(workspace, repo):
    commit_file(repo, "a.txt", "hello\n", "feat: something worth reporting")
    before = snapshot(workspace["build_dir"])

    main(workspace["argv"] + ["--dry-run"])

    assert snapshot(workspace["build_dir"]) == before
    # fetch_memo() used to create memo.md as a side effect of reading it.
    assert not (workspace["build_dir"] / "memo.md").exists()


def test_no_commits_leaves_the_build_directory_untouched(workspace, repo):
    """The run fails, but the stale prompt and the filled-in report survive."""
    commit_file(repo, "a.txt", "hello\n", "feat: not mine", author=OTHER_AUTHOR)
    before = snapshot(workspace["build_dir"])

    with pytest.raises(SystemExit) as exc_info:
        main(workspace["argv"])

    assert exc_info.value.code == 1
    assert snapshot(workspace["build_dir"]) == before


def test_successful_run_archives_the_report_and_writes_a_new_prompt(workspace, repo):
    commit_file(repo, "a.txt", "hello\n", "feat: something worth reporting")
    build_dir = workspace["build_dir"]

    main(workspace["argv"])

    # The stale prompt is gone, replaced by exactly one new one.
    prompts = sorted(build_dir.glob("prompt-*.md"))
    assert len(prompts) == 1
    assert prompts[0].name != STALE_PROMPT

    # Last week's report moved to history; a fresh blank one took its place.
    assert (build_dir / "history" / FILLED_REPORT).read_text() == FILLED_REPORT_BODY
    assert not (build_dir / FILLED_REPORT).exists()

    reports = sorted(build_dir.glob("report-*.md"))
    assert len(reports) == 1
    assert reports[0].read_text(encoding="utf-8") == REPORT_BLANK_MESSAGE

    assert (build_dir / "memo.md").exists()


def test_prompt_carries_last_weeks_report_and_this_weeks_commits(workspace, repo):
    """The report still in build/ must reach the prompt, not be archived out from under it."""
    commit_file(repo, "a.txt", "hello\n", "feat: something worth reporting")

    main(workspace["argv"])

    prompt = next(workspace["build_dir"].glob("prompt-*.md")).read_text(encoding="utf-8")

    assert "shipped the thing" in prompt
    assert "feat: something worth reporting" in prompt
    assert "my-project" in prompt


def test_commits_are_collected_since_the_unarchived_report(workspace, repo):
    """The cutoff comes from the report in build/, so older commits stay out."""
    commit_file(repo, "old.txt", "old\n", "feat: long before the last report")
    old_date = datetime(2025, 1, 1, 12, 0, 0).isoformat()
    repo.git.commit(
        "--amend",
        "--no-edit",
        date=old_date,
        env={
            "GIT_COMMITTER_DATE": old_date,
        },
    )
    commit_file(repo, "new.txt", "new\n", "feat: after the last report")

    main(workspace["argv"])

    prompt = next(workspace["build_dir"].glob("prompt-*.md")).read_text(encoding="utf-8")

    assert "feat: after the last report" in prompt
    assert "feat: long before the last report" not in prompt

"""End-to-end tests driving main() against real repositories and a real home directory.

These exist because the interesting failures are side effects: the order of the write
phase, what a failed run leaves behind, and what the JSON promises to the skills in
docs/contract.md. Only a test that looks at the filesystem can catch those.
"""

import json
from datetime import datetime, timedelta

import pytest
import yaml

from weekly_report.main import main
from weekly_report.report_file_manager import ReportFileManager

pytestmark = pytest.mark.integration


def run_cli(capsys, *argv) -> tuple[int, dict]:
    exit_code = main(list(argv))
    output = capsys.readouterr().out
    return exit_code, json.loads(output)


def configure(home, repos: list[dict], author="Test Author", **overrides):
    home.root.mkdir(parents=True, exist_ok=True)
    config = {"author": author, "lang": "korean", "repository": repos, **overrides}
    home.config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    home.template_path.write_text("# {date}\n\n## Work Done\n* {item}\n", encoding="utf-8")


class TestRun:
    def test_not_configured(self, home, capsys):
        exit_code, payload = run_cli(capsys, "run", "--json")
        assert exit_code == 2
        assert payload["schema_version"] == 1
        assert payload["status"] == "not_configured"
        assert payload["paths"]["prompt"] is None
        assert payload["warnings"]

    def test_empty_repository_list_is_not_configured(self, home, capsys):
        configure(home, repos=[])
        exit_code, payload = run_cli(capsys, "run", "--json")
        assert exit_code == 2
        assert payload["status"] == "not_configured"

    def test_unreadable_repository(self, home, tmp_path, capsys):
        configure(home, repos=[{"path": str(tmp_path / "gone")}])
        exit_code, payload = run_cli(capsys, "run", "--json")
        assert exit_code == 3
        assert payload["status"] == "repo_error"
        assert "gone" in payload["warnings"][0]

    def test_first_run_falls_back_to_seven_days(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: work")
        configure(home, repos=[{"path": str(repo_path), "name": "Athena"}])

        exit_code, payload = run_cli(capsys, "run", "--json")

        assert exit_code == 0
        assert payload["status"] == "ok"
        assert payload["period"]["since_source"] == "fallback_7d"
        assert payload["repositories"][0] == {
            "name": "Athena",
            "path": str(repo_path),
            "commits": 1,
            "insertions": 1,
            "deletions": 0,
            "files_changed": 1,
            "authors": ["Test Author"],
        }
        assert payload["totals"]["commits"] == 1
        assert payload["tokens"]["method"] == "heuristic"
        assert not payload["tokens"]["over_threshold"]

        # The write phase really happened: prompt.md and a blank, marked report.md.
        assert home.prompt_path.read_text(encoding="utf-8").startswith("# Weekly Work Report Request")
        report_text = home.report_path.read_text(encoding="utf-8")
        assert "weekly-report: created" in report_text

    def test_weekly_cycle_archives_and_continues_from_history(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: week one")
        configure(home, repos=[{"path": str(repo_path)}])
        run_cli(capsys, "run", "--json")

        # The agent writes the report below the created marker.
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("\n# 7/30\n* week one work\n")
        commit_in(repo_path, message="feat: week two")

        exit_code, payload = run_cli(capsys, "run", "--json")

        assert exit_code == 0
        assert payload["period"]["since_source"] == "history"
        assert payload["history"]["count"] == 1
        archived = list(home.history_dir.glob("report-*.md"))
        assert len(archived) == 1
        assert "week one work" in archived[0].read_text(encoding="utf-8")
        # since equals the archived report's date, so nothing is lost between runs.
        assert payload["period"]["since"] == payload["history"]["latest"]

    def test_no_commits_leaves_files_alone(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: only old work", date="2020-01-01T09:00:00")
        configure(home, repos=[{"path": str(repo_path)}])
        manager = ReportFileManager(home, history_limit=5)
        manager.create_blank_report(created=datetime(2026, 7, 23, 9, 0, 0))
        with home.report_path.open("a", encoding="utf-8") as f:
            f.write("precious report\n")

        exit_code, payload = run_cli(capsys, "run", "--json")

        assert exit_code == 1
        assert payload["status"] == "no_commits"
        assert payload["paths"]["prompt"] is None
        assert not home.prompt_path.exists()
        assert "precious report" in home.report_path.read_text(encoding="utf-8")

    def test_dry_run_writes_nothing(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: work")
        configure(home, repos=[{"path": str(repo_path)}])

        exit_code, payload = run_cli(capsys, "run", "--dry-run", "--json")

        assert exit_code == 0
        assert payload["status"] == "ok"
        assert payload["dry_run"] is True
        assert payload["paths"]["prompt"] is None
        assert not home.prompt_path.exists()
        assert not home.report_path.exists()

    def test_over_threshold_warns(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: work")
        configure(home, repos=[{"path": str(repo_path)}], large_prompt_tokens=1)

        _, payload = run_cli(capsys, "run", "--dry-run", "--json")

        assert payload["tokens"]["over_threshold"] is True
        assert any("threshold" in warning for warning in payload["warnings"])

    def test_zero_commit_repository_warns_by_name(self, home, make_repo, commit_in, capsys):
        active = make_repo("active")
        commit_in(active, message="feat: work")
        idle = make_repo("idle")
        commit_in(idle, message="feat: someone else's", author="someone.else", email="s@example.com")
        configure(home, repos=[{"path": str(active)}, {"path": str(idle), "name": "Idle"}])

        exit_code, payload = run_cli(capsys, "run", "--dry-run", "--json")

        assert exit_code == 0
        assert any("'Idle' has no commits" in warning for warning in payload["warnings"])

    def test_approximate_boundary_warning_survives_dry_run(
        self, home, tmp_path, make_repo, commit_in, capsys
    ):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: boundary work")
        configure(home, repos=[{"path": str(repo_path)}])
        source = tmp_path / "old.md"
        source.write_text("# old report\n", encoding="utf-8")
        boundary = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        run_cli(capsys, "history", "import", str(source), "--date", boundary, "--json")

        first_exit, first = run_cli(capsys, "run", "--dry-run", "--json")
        second_exit, second = run_cli(capsys, "run", "--dry-run", "--json")

        assert first_exit == second_exit == 0
        assert first["period"]["since"] == f"{boundary}T00:00:00"
        assert any("first collection includes the entire boundary day" in warning for warning in first["warnings"])
        assert second["warnings"] == first["warnings"]

    def test_exact_written_report_clears_approximate_warning(
        self, home, tmp_path, make_repo, commit_in, capsys
    ):
        repo_path = make_repo()
        commit_in(repo_path, message="feat: first report")
        configure(home, repos=[{"path": str(repo_path)}])
        source = tmp_path / "old.md"
        source.write_text("# old report\n", encoding="utf-8")
        boundary = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        run_cli(capsys, "history", "import", str(source), "--date", boundary, "--json")

        first_exit, first = run_cli(capsys, "run", "--json")
        assert first_exit == 0
        assert any("first collection includes the entire boundary day" in warning for warning in first["warnings"])
        with home.report_path.open("a", encoding="utf-8") as report:
            report.write("# first exact report\n* worked\n")
        commit_in(repo_path, message="feat: next report", filename="next.txt")

        second_exit, second = run_cli(capsys, "run", "--dry-run", "--json")

        assert second_exit == 0
        assert second["period"]["since"] == first["period"]["until"]
        assert not any("first collection includes the entire boundary day" in warning for warning in second["warnings"])

    def test_no_commits_does_not_consume_approximate_warning(
        self, home, tmp_path, make_repo, commit_in, capsys
    ):
        repo_path = make_repo()
        commit_in(repo_path, message="old", date="2020-01-01T09:00:00")
        configure(home, repos=[{"path": str(repo_path)}])
        source = tmp_path / "old.md"
        source.write_text("# old report\n", encoding="utf-8")
        boundary = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        run_cli(capsys, "history", "import", str(source), "--date", boundary, "--json")

        no_commit_exit, no_commit = run_cli(capsys, "run", "--json")
        commit_in(repo_path, message="new")
        retry_exit, retry = run_cli(capsys, "run", "--dry-run", "--json")

        assert no_commit_exit == 1
        assert any(
            "first collection includes the entire boundary day" in warning for warning in no_commit["warnings"]
        )
        assert retry_exit == 0
        assert any("first collection includes the entire boundary day" in warning for warning in retry["warnings"])


class TestRepo:
    def test_add_normalizes_to_root_and_warns_on_no_recent_commits(self, home, make_repo, commit_in, capsys):
        configure(home, repos=[])
        repo_path = make_repo()
        commit_in(repo_path, message="feat: someone else's", author="someone.else", email="s@example.com")
        sub = repo_path / "src"
        sub.mkdir()

        exit_code, payload = run_cli(capsys, "repo", "add", str(sub), "--name", "Athena", "--json")

        assert exit_code == 0
        assert payload["added"]["name"] == "Athena"
        assert payload["added"]["path"] == str(repo_path.resolve())
        assert any("no commits by" in warning for warning in payload["warnings"])

        saved = yaml.safe_load(home.config_path.read_text(encoding="utf-8"))
        assert saved["repository"] == [{"path": str(repo_path.resolve()), "name": "Athena"}]

    def test_add_rejects_non_repository(self, home, tmp_path, capsys):
        configure(home, repos=[])
        plain = tmp_path / "plain"
        plain.mkdir()

        exit_code, payload = run_cli(capsys, "repo", "add", str(plain), "--json")

        assert exit_code == 3
        assert payload["status"] == "repo_error"

    def test_add_is_idempotent_for_registered_repo(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo()
        commit_in(repo_path)
        configure(home, repos=[{"path": str(repo_path), "name": "Athena"}])

        exit_code, payload = run_cli(capsys, "repo", "add", str(repo_path), "--json")

        assert exit_code == 0
        assert payload["added"] is None
        assert any("already registered" in warning for warning in payload["warnings"])
        saved = yaml.safe_load(home.config_path.read_text(encoding="utf-8"))
        assert len(saved["repository"]) == 1

    def test_add_with_explicit_authors(self, home, make_repo, commit_in, capsys):
        configure(home, repos=[])
        repo_path = make_repo()
        commit_in(repo_path, author="mjkim", email="m@example.com")

        exit_code, payload = run_cli(
            capsys, "repo", "add", str(repo_path), "--author", "mjkim", "--author", "minjae.kim", "--json"
        )

        assert exit_code == 0
        assert payload["added"]["authors"] == ["mjkim", "minjae.kim"]
        assert payload["warnings"] == []

    def test_list(self, home, make_repo, capsys):
        repo_path = make_repo()
        configure(home, repos=[{"path": str(repo_path), "name": "Athena", "authors": ["mjkim"]}])

        exit_code, payload = run_cli(capsys, "repo", "list", "--json")

        assert exit_code == 0
        assert payload["repositories"] == [{"name": "Athena", "path": str(repo_path), "authors": ["mjkim"]}]

    def test_remove_by_name(self, home, make_repo, capsys):
        repo_path = make_repo()
        configure(home, repos=[{"path": str(repo_path), "name": "Athena"}])

        exit_code, payload = run_cli(capsys, "repo", "remove", "Athena", "--json")

        assert exit_code == 0
        assert payload["removed"]["name"] == "Athena"
        assert yaml.safe_load(home.config_path.read_text(encoding="utf-8"))["repository"] == []

    def test_remove_by_path(self, home, make_repo, capsys):
        repo_path = make_repo()
        configure(home, repos=[{"path": str(repo_path)}])

        exit_code, payload = run_cli(capsys, "repo", "remove", str(repo_path), "--json")

        assert exit_code == 0
        assert payload["removed"]["path"] == str(repo_path)

    def test_remove_unknown_target_warns(self, home, make_repo, capsys):
        repo_path = make_repo()
        configure(home, repos=[{"path": str(repo_path), "name": "Athena"}])

        exit_code, payload = run_cli(capsys, "repo", "remove", "Nope", "--json")

        assert exit_code == 0
        assert payload["removed"] is None
        assert any("not registered" in warning for warning in payload["warnings"])
        assert len(yaml.safe_load(home.config_path.read_text(encoding="utf-8"))["repository"]) == 1

    def test_commands_require_config(self, home, capsys):
        exit_code, payload = run_cli(capsys, "repo", "list", "--json")
        assert exit_code == 2
        assert payload["status"] == "not_configured"


class TestAuthors:
    def test_candidates_with_git_user_name(self, home, make_repo, commit_in, capsys):
        repo_path = make_repo(user_name="Configured Name")
        commit_in(repo_path, author="actual.author", email="a@example.com")
        commit_in(repo_path, author="actual.author", email="a@example.com")

        exit_code, payload = run_cli(capsys, "authors", str(repo_path), "--json")

        assert exit_code == 0
        (info,) = payload["repositories"]
        assert info["git_user_name"] == "Configured Name"
        assert info["authors"] == [{"name": "actual.author", "email": "a@example.com", "commits": 2}]

    def test_non_repository_fails_with_exit_3(self, home, tmp_path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()
        exit_code, payload = run_cli(capsys, "authors", str(plain), "--json")
        assert exit_code == 3
        assert payload["status"] == "repo_error"


class TestHistoryImport:
    def make_reports(self, tmp_path, count):
        files = []
        for index in range(count):
            path = tmp_path / f"old-{index}.md"
            path.write_text(f"# old report {index}\n", encoding="utf-8")
            files.append(path)
        return files

    def test_weekly_from_steps_back_seven_days(self, home, tmp_path, capsys):
        first, second = self.make_reports(tmp_path, 2)

        exit_code, payload = run_cli(
            capsys, "history", "import", str(first), str(second), "--weekly-from", "2026-07-23", "--json"
        )

        assert exit_code == 0
        names = sorted(path.name for path in home.history_dir.iterdir())
        assert names == ["report-20260716-000000.md", "report-20260723-000000.md"]
        assert payload["imported"][0]["date"] == "2026-07-23T00:00:00"
        assert payload["imported"][1]["date"] == "2026-07-16T00:00:00"

    def test_date_imports_a_single_file(self, home, tmp_path, capsys):
        (report,) = self.make_reports(tmp_path, 1)

        exit_code, _ = run_cli(capsys, "history", "import", str(report), "--date", "2026-07-23", "--json")

        assert exit_code == 0
        assert (home.history_dir / "report-20260723-000000.md").exists()

    def test_date_import_marks_boundary_and_warns(self, home, tmp_path, capsys):
        (report,) = self.make_reports(tmp_path, 1)

        exit_code, payload = run_cli(
            capsys,
            "history",
            "import",
            str(report),
            "--date",
            "2026-07-30",
            "--json",
        )

        assert exit_code == 0
        imported = home.history_dir / "report-20260730-000000.md"
        assert imported.read_text(encoding="utf-8").startswith(
            "[//]: # (weekly-report: boundary approximate date-only)\n"
        )
        assert payload["imported"][0]["date"] == "2026-07-30T00:00:00"
        assert payload["warnings"] == [
            "Onboarding only knows the imported report's date, not its exact cutoff time. "
            "To avoid missing commits, the first collection includes the entire boundary day (2026-07-30). "
            "Some work may overlap with the imported report, so please review the generated draft for duplicate items."
        ]

    def test_date_with_multiple_files_is_rejected(self, home, tmp_path, capsys):
        first, second = self.make_reports(tmp_path, 2)
        exit_code, payload = run_cli(
            capsys, "history", "import", str(first), str(second), "--date", "2026-07-23", "--json"
        )
        assert exit_code == 2
        assert "single file" in payload["warnings"][0]

    def test_requires_exactly_one_date_flag(self, home, tmp_path, capsys):
        (report,) = self.make_reports(tmp_path, 1)
        exit_code, payload = run_cli(capsys, "history", "import", str(report), "--json")
        assert exit_code == 2
        assert "exactly one" in payload["warnings"][0]

    def test_missing_source_file_is_rejected(self, home, tmp_path, capsys):
        exit_code, payload = run_cli(
            capsys, "history", "import", str(tmp_path / "nope.md"), "--date", "2026-07-23", "--json"
        )
        assert exit_code == 2
        assert "file not found" in payload["warnings"][0]

    def test_refuses_to_overwrite_existing_archive(self, home, tmp_path, capsys):
        (report,) = self.make_reports(tmp_path, 1)
        run_cli(capsys, "history", "import", str(report), "--date", "2026-07-23", "--json")

        exit_code, payload = run_cli(capsys, "history", "import", str(report), "--date", "2026-07-23", "--json")

        assert exit_code == 2
        assert "already in history" in payload["warnings"][0]

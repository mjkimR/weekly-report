"""The weekly-report CLI.

Agent skills call these commands with --json and parse the output; the JSON shapes and
exit codes are the contract in docs/contract.md. Human-readable output is a plain
summary -- the reader is usually an agent, so there is nothing decorative here.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import git

from weekly_report.config_loader import ConfigError, load_config, load_template, save_config
from weekly_report.git_data_collector import (
    GitDataCollector,
    author_candidates,
    configured_user_name,
    has_commits_by,
    open_repository,
)
from weekly_report.paths import Home
from weekly_report.prompt_generator import (
    TOKEN_ESTIMATE_METHOD,
    PromptGenerator,
    approximate_tokens,
)
from weekly_report.report_file_manager import ReportFileManager, import_report
from weekly_report.schemas import CommitDataSummary, RepositoryEntry

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_NO_COMMITS = 1
EXIT_NOT_CONFIGURED = 2
EXIT_REPO_ERROR = 3

AUTHOR_CANDIDATE_DAYS = 180
RECENT_COMMIT_CHECK_DAYS = 90

ISO_SECONDS = "%Y-%m-%dT%H:%M:%S"


def _iso(date: datetime | None) -> str | None:
    return date.strftime(ISO_SECONDS) if date else None


def _approximate_boundary_warning(date: datetime) -> str:
    return (
        "Onboarding only knows the imported report's date, not its exact cutoff time. "
        f"To avoid missing commits, the first collection includes the entire boundary day ({date:%Y-%m-%d}). "
        "Some work may overlap with the imported report, so please review the generated draft for duplicate items."
    )


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def summarize_commit_data(commits) -> CommitDataSummary:
    """Generate summary information for Git data."""
    return CommitDataSummary(
        start_date=min([commit.date for commit in commits], default=datetime.now()),
        end_date=max([commit.date for commit in commits], default=datetime.now()),
        total_commits=len(commits),
        total_insertions=sum(commit.stats.insertions for commit in commits),
        total_deletions=sum(commit.stats.deletions for commit in commits),
        # A file touched by three commits is one changed file, not three.
        total_files_changed=len({path for commit in commits for path in commit.stats.changed_files}),
    )


# --- run ---


def _run_payload(
    status: str,
    dry_run: bool,
    home: Home,
    period: dict | None = None,
    repositories: list[dict] | None = None,
    totals: dict | None = None,
    history: dict | None = None,
    tokens: dict | None = None,
    prompt_path: Path | None = None,
    report_path: Path | None = None,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "dry_run": dry_run,
        "period": period,
        "repositories": repositories or [],
        "totals": totals,
        "history": history,
        "tokens": tokens,
        "paths": {
            "prompt": str(prompt_path) if prompt_path else None,
            "report": str(report_path) if report_path else None,
            "home": str(home.root),
        },
        "warnings": warnings or [],
    }


def cmd_run(args) -> int:
    home = Home()
    now = datetime.now().replace(microsecond=0)
    warnings: list[str] = []

    try:
        config = load_config(home)
        template = load_template(home)
    except ConfigError as error:
        return _emit_run_failure(args, home, "not_configured", [str(error)], EXIT_NOT_CONFIGURED)

    if not config.repository:
        message = "no repositories configured; run the weekly-report-onboard skill or `weekly-report repo add`"
        return _emit_run_failure(args, home, "not_configured", [message], EXIT_NOT_CONFIGURED)

    manager = ReportFileManager(home, config.report_history_limit)

    if manager.report_md_is_filled():
        _, used_mtime = manager.report_md_date()
        if used_mtime:
            warnings.append(
                "report.md has lost its 'created' marker; using the file's modification time "
                "as the end of the reported period"
            )

    last_boundary = manager.last_report_boundary()
    if last_boundary is not None:
        last_report_date, approximate_boundary = last_boundary
        since, since_source = last_report_date, "history"
        if approximate_boundary:
            warnings.append(_approximate_boundary_warning(since))
    else:
        last_report_date = None
        since = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0)
        since_source = "fallback_7d"
    period = {"since": _iso(since), "until": _iso(now), "since_source": since_source}

    # Everything up to the write phase is read-only: a run that finds no commits, or a
    # --dry-run, must leave the home directory exactly as it found it.
    previous_reports = manager.fetch_report_history()

    repositories = []
    project_data = []
    for entry in config.repository:
        authors = entry.effective_authors(config.author)
        try:
            collector = GitDataCollector(entry.path, authors)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            warnings.append(f"cannot read repository: {entry.path} (fix it with the weekly-report-repos skill)")
            payload = _run_payload("repo_error", args.dry_run, home, period=period, warnings=warnings)
            return _emit_run(args, payload, EXIT_REPO_ERROR)

        commits = collector.collect_commits(since)
        summary = summarize_commit_data(commits)
        name = entry.display_name()
        project_data.append(
            {"project_name": name, "repo_path": entry.path, "recent_commits": commits, "summary": summary}
        )
        repositories.append(
            {
                "name": name,
                "path": entry.path,
                "commits": summary.total_commits,
                "insertions": summary.total_insertions,
                "deletions": summary.total_deletions,
                "files_changed": summary.total_files_changed,
                "authors": authors,
            }
        )

    totals = {
        "commits": sum(repo["commits"] for repo in repositories),
        "insertions": sum(repo["insertions"] for repo in repositories),
        "deletions": sum(repo["deletions"] for repo in repositories),
        "files_changed": sum(repo["files_changed"] for repo in repositories),
    }

    history_info = {
        "count": len(manager.known_reports()),
        "latest": _iso(last_report_date),
    }

    if totals["commits"] == 0:
        warnings.append(f"no commits found between {_iso(since)} and {_iso(now)}; nothing was written")
        payload = _run_payload(
            "no_commits",
            args.dry_run,
            home,
            period=period,
            repositories=repositories,
            totals=totals,
            history=history_info,
            warnings=warnings,
        )
        return _emit_run(args, payload, EXIT_NO_COMMITS)

    for repo in repositories:
        if repo["commits"] == 0:
            warnings.append(f"repository '{repo['name']}' has no commits in this period")

    generator = PromptGenerator(
        project_data=project_data,
        template=template,
        lang=config.lang,
        max_diff_lines=config.max_diff_lines,
        previous_reports=previous_reports,
    )
    prompt = generator.generate_prompt()

    estimate = approximate_tokens(prompt)
    tokens = {
        "estimate": estimate,
        "method": TOKEN_ESTIMATE_METHOD,
        "threshold": config.large_prompt_tokens,
        "over_threshold": estimate > config.large_prompt_tokens,
    }
    if tokens["over_threshold"]:
        warnings.append(
            f"prompt is roughly {estimate} tokens, over the {config.large_prompt_tokens} threshold; "
            "consider lowering max_diff_lines in config.yaml"
        )

    prompt_path = None
    report_path = None
    if not args.dry_run:
        # Order matters: archive the previous report before anything else so a failure
        # halfway through never loses it. See docs/contract.md.
        manager.archive_report_md()
        manager.trim_history()
        prompt_path = manager.write_prompt(prompt)
        report_path = manager.create_blank_report(created=now)
        history_info = {
            "count": len(manager.known_reports()),
            "latest": _iso(manager.last_report_date()),
        }

    payload = _run_payload(
        "ok",
        args.dry_run,
        home,
        period=period,
        repositories=repositories,
        totals=totals,
        history=history_info,
        tokens=tokens,
        prompt_path=prompt_path,
        report_path=report_path,
        warnings=warnings,
    )
    return _emit_run(args, payload, EXIT_OK)


def _emit_run(args, payload: dict, exit_code: int) -> int:
    if args.json:
        _print_json(payload)
        return exit_code

    period = payload["period"]
    if period:
        print(f"period: {period['since']} ~ {period['until']} ({period['since_source']})")
    for repo in payload["repositories"]:
        print(
            f"{repo['name']}: {repo['commits']} commits, "
            f"+{repo['insertions']}/-{repo['deletions']}, {repo['files_changed']} files"
        )
    totals = payload["totals"]
    if totals:
        print(f"total: {totals['commits']} commits")
    tokens = payload["tokens"]
    if tokens:
        print(f"tokens: ~{tokens['estimate']} ({tokens['method']}, threshold {tokens['threshold']})")
    if payload["paths"]["prompt"]:
        print(f"prompt: {payload['paths']['prompt']}")
        print(f"report: {payload['paths']['report']}")
    if payload["dry_run"]:
        print("dry run: nothing was written")
    _print_warnings(payload["warnings"])
    return exit_code


def _emit_run_failure(args, home: Home, status: str, warnings: list[str], exit_code: int) -> int:
    payload = _run_payload(status, args.dry_run, home, warnings=warnings)
    if args.json:
        _print_json(payload)
    else:
        _print_warnings(warnings)
    return exit_code


# --- repo ---


def _repo_row(entry: RepositoryEntry, global_author: str | None) -> dict:
    return {
        "name": entry.display_name(),
        "path": entry.path,
        "authors": entry.effective_authors(global_author),
    }


def _emit_simple(args, payload: dict, exit_code: int, human_lines: list[str]) -> int:
    if args.json:
        _print_json(payload)
    else:
        for line in human_lines:
            print(line)
        _print_warnings(payload.get("warnings", []))
    return exit_code


def _fail(args, status: str, message: str, exit_code: int) -> int:
    """Uniform failure shape for the non-run commands: JSON envelope or one stderr line."""
    if args.json:
        _print_json({"schema_version": SCHEMA_VERSION, "status": status, "warnings": [message]})
    else:
        print(f"error: {message}", file=sys.stderr)
    return exit_code


def cmd_repo_list(args) -> int:
    home = Home()
    try:
        config = load_config(home)
    except ConfigError as error:
        return _fail(args, "not_configured", str(error), EXIT_NOT_CONFIGURED)

    rows = [_repo_row(entry, config.author) for entry in config.repository]
    payload = {"schema_version": SCHEMA_VERSION, "status": "ok", "repositories": rows, "warnings": []}
    lines = [f"{row['name']}: {row['path']} (authors: {', '.join(row['authors'])})" for row in rows] or [
        "no repositories configured"
    ]
    return _emit_simple(args, payload, EXIT_OK, lines)


def cmd_repo_add(args) -> int:
    home = Home()
    try:
        config = load_config(home)
    except ConfigError as error:
        return _fail(args, "not_configured", str(error), EXIT_NOT_CONFIGURED)

    try:
        repo = open_repository(str(Path(args.path).expanduser()))
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return _fail(args, "repo_error", f"not a git repository: {args.path}", EXIT_REPO_ERROR)

    root = Path(str(repo.working_tree_dir)).resolve()
    warnings: list[str] = []
    if str(root) != str(Path(args.path).expanduser().resolve()):
        warnings.append(f"registered the repository root: {root}")

    for entry in config.repository:
        if Path(entry.path).expanduser().resolve() == root:
            warnings.append(f"already registered as '{entry.display_name()}'")
            payload = {
                "schema_version": SCHEMA_VERSION,
                "status": "ok",
                "added": None,
                "repository": _repo_row(entry, config.author),
                "warnings": warnings,
            }
            # No human line: _emit_simple already prints the warning, and a second
            # "already registered" line would just repeat it.
            return _emit_simple(args, payload, EXIT_OK, [])

    entry = RepositoryEntry(path=str(root), name=args.name, authors=args.authors or None)
    authors = entry.effective_authors(config.author)
    if not authors:
        message = "no --author given and no global author in config.yaml"
        return _fail(args, "not_configured", message, EXIT_NOT_CONFIGURED)

    # Catch author-name mismatches at registration time instead of as silent zeroes
    # in every later run.
    since = datetime.now() - timedelta(days=RECENT_COMMIT_CHECK_DAYS)
    if not has_commits_by(repo, authors, since):
        warnings.append(
            f"no commits by {authors} in the last {RECENT_COMMIT_CHECK_DAYS} days; "
            f"check the author name with `weekly-report authors {root}`"
        )

    config.repository.append(entry)
    save_config(home, config)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "added": _repo_row(entry, config.author),
        "warnings": warnings,
    }
    return _emit_simple(args, payload, EXIT_OK, [f"added: {entry.display_name()} ({root})"])


def cmd_repo_remove(args) -> int:
    home = Home()
    try:
        config = load_config(home)
    except ConfigError as error:
        return _fail(args, "not_configured", str(error), EXIT_NOT_CONFIGURED)

    target_path = Path(args.target).expanduser()
    removed = None
    for entry in config.repository:
        if entry.display_name() == args.target or Path(entry.path).expanduser() == target_path:
            removed = entry
            break
    # A resolve()-based pass would also match symlinked paths, but only try it when the
    # target looks like a path that exists; resolve() on a name like "Athena" is noise.
    if removed is None and target_path.exists():
        resolved = target_path.resolve()
        for entry in config.repository:
            if Path(entry.path).expanduser().resolve() == resolved:
                removed = entry
                break

    if removed is None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "removed": None,
            "warnings": [f"not registered: {args.target}"],
        }
        return _emit_simple(args, payload, EXIT_OK, [f"not registered: {args.target}"])

    config.repository.remove(removed)
    save_config(home, config)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "removed": _repo_row(removed, config.author),
        "warnings": [],
    }
    return _emit_simple(args, payload, EXIT_OK, [f"removed: {removed.display_name()} ({removed.path})"])


# --- authors ---


def cmd_authors(args) -> int:
    since = datetime.now() - timedelta(days=AUTHOR_CANDIDATE_DAYS)
    repositories = []
    for path in args.paths:
        try:
            repo = open_repository(str(Path(path).expanduser()))
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            return _fail(args, "repo_error", f"not a git repository: {path}", EXIT_REPO_ERROR)

        repositories.append(
            {
                "path": path,
                "root": str(repo.working_tree_dir),
                "git_user_name": configured_user_name(repo),
                "authors": author_candidates(repo, since),
            }
        )

    payload = {"schema_version": SCHEMA_VERSION, "status": "ok", "repositories": repositories, "warnings": []}
    lines = []
    for repo_info in repositories:
        lines.append(f"{repo_info['root']} (git config user.name: {repo_info['git_user_name']})")
        for candidate in repo_info["authors"]:
            lines.append(f"  {candidate['name']} <{candidate['email']}>: {candidate['commits']} commits")
        if not repo_info["authors"]:
            lines.append(f"  no commits in the last {AUTHOR_CANDIDATE_DAYS} days")
    return _emit_simple(args, payload, EXIT_OK, lines)


# --- history import ---


def cmd_history_import(args) -> int:
    def usage_error(message: str) -> int:
        return _fail(args, "not_configured", message, EXIT_NOT_CONFIGURED)

    # Dates are never guessed from file contents: report titles rarely carry a year, and
    # a wrong date silently shifts the next collection window.
    if bool(args.date) == bool(args.weekly_from):
        return usage_error("give exactly one of --date or --weekly-from")
    if args.date and len(args.files) > 1:
        return usage_error("--date only applies to a single file; use --weekly-from for several")

    raw_date = args.date or args.weekly_from
    try:
        first_date = datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        return usage_error(f"not a YYYY-MM-DD date: {raw_date}")

    sources = [Path(name).expanduser() for name in args.files]
    for source in sources:
        if not source.is_file():
            return usage_error(f"file not found: {source}")

    home = Home()

    imported = []
    try:
        for index, source in enumerate(sources):
            date = first_date - timedelta(days=7 * index)
            date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            destination = import_report(home, source, date, approximate_boundary=True)
            imported.append({"source": str(source), "path": str(destination), "date": _iso(date)})
    except FileExistsError as error:
        return usage_error(str(error))

    warnings = [_approximate_boundary_warning(first_date)]
    payload = {"schema_version": SCHEMA_VERSION, "status": "ok", "imported": imported, "warnings": warnings}
    lines = [f"imported: {item['source']} -> {item['path']}" for item in imported]
    return _emit_simple(args, payload, EXIT_OK, lines)


# --- entry point ---


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weekly-report",
        description="Collect Git commits and build the prompt for a weekly development report.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Collect commits and write prompt.md and a blank report.md.")
    run_parser.add_argument("--json", action="store_true", help="Emit one JSON object on stdout.")
    run_parser.add_argument("--dry-run", action="store_true", help="Write nothing; only report what was collected.")
    run_parser.set_defaults(handler=cmd_run)

    repo_parser = subparsers.add_parser("repo", help="Manage the repositories the report covers.")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", required=True)

    repo_list = repo_subparsers.add_parser("list", help="Show the configured repositories.")
    repo_list.add_argument("--json", action="store_true")
    repo_list.set_defaults(handler=cmd_repo_list)

    repo_add = repo_subparsers.add_parser("add", help="Register a repository.")
    repo_add.add_argument("path")
    repo_add.add_argument("--name", help="Display name used in the report (default: last path segment).")
    repo_add.add_argument(
        "--author",
        action="append",
        dest="authors",
        help="Commit author to match in this repository; repeatable. Default: the global author.",
    )
    repo_add.add_argument("--json", action="store_true")
    repo_add.set_defaults(handler=cmd_repo_add)

    repo_remove = repo_subparsers.add_parser("remove", help="Unregister a repository by name or path.")
    repo_remove.add_argument("target")
    repo_remove.add_argument("--json", action="store_true")
    repo_remove.set_defaults(handler=cmd_repo_remove)

    authors_parser = subparsers.add_parser("authors", help="List commit author candidates for repositories.")
    authors_parser.add_argument("paths", nargs="+")
    authors_parser.add_argument("--json", action="store_true")
    authors_parser.set_defaults(handler=cmd_authors)

    history_parser = subparsers.add_parser("history", help="Manage archived reports.")
    history_subparsers = history_parser.add_subparsers(dest="history_command", required=True)

    history_import = history_subparsers.add_parser("import", help="Seed history/ with existing report files.")
    history_import.add_argument("files", nargs="+")
    history_import.add_argument("--date", help="Date (YYYY-MM-DD) of the single given file.")
    history_import.add_argument(
        "--weekly-from",
        dest="weekly_from",
        help="Date (YYYY-MM-DD) of the first file; each following file goes 7 days further back.",
    )
    history_import.add_argument("--json", action="store_true")
    history_import.set_defaults(handler=cmd_history_import)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

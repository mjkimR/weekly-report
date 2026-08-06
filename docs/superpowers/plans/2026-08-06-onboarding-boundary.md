# Safe Onboarding Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make date-only onboarding start at the boundary day's midnight, preserve that uncertainty in history, and warn only until the first exact report boundary exists.

**Architecture:** Store boundary uncertainty as a bookkeeping comment in imported history reports so `history/` remains the only persistent state. `ReportFileManager` exposes the latest boundary as `(datetime, approximate)`, while the CLI owns the canonical English warning and the two user-facing skills translate warnings into the latest request's language.

**Tech Stack:** Python 3.12, pathlib, GitPython, pytest, Markdown-based Codex skills, uv

## Global Constraints

- Date-only imports use `00:00:00`; commit omission is forbidden even if this creates overlap.
- The exact marker is `[//]: # (weekly-report: boundary approximate date-only)`.
- The canonical CLI warning is: `Onboarding only knows the imported report's date, not its exact cutoff time. To avoid missing commits, the first collection includes the entire boundary day ({date}). Some work may overlap with the imported report, so please review the generated draft for duplicate items.`
- `{date}` is a runtime placeholder rendered as `YYYY-MM-DD`; it is not unresolved plan work.
- CLI warning strings remain English. Skills translate them into the language of the user's latest request while preserving dates, file paths, commands, and technical identifiers.
- Existing markerless history remains unchanged and is treated as exact; do not migrate existing `09:00:00` files.
- Do not add a full-timestamp import flag, a sidecar state file, a commit ledger, or a new dependency.
- Preserve the existing JSON schema, exit codes, report format, and exact-boundary weekly cycle.
- Prepare the backward-compatible bug-fix release as `0.2.1`; do not create or push the Git tag in this plan.
- Preserve the user's existing `.gitignore` modification and exclude it from every commit.

## File Map

- `weekly_report/report_file_manager.py`: approximate marker persistence, stripping, detection, and latest-boundary metadata.
- `weekly_report/main.py`: canonical warning rendering, midnight import, and run-time warning lifecycle.
- `tests/unit/test_report_file_manager.py`: focused marker and boundary metadata tests.
- `tests/integration/test_main_cli.py`: import output and first-run warning lifecycle tests.
- `skills/weekly-report/SKILL.md`: translate CLI warnings and repeat the approximate warning in the final handoff.
- `skills/weekly-report-onboard/SKILL.md`: consume JSON import warnings, translate them, and explain expected first-run overlap.
- `tests/unit/test_skill_warning_contract.py`: static checks that both skill contracts retain localization requirements.
- `docs/contract.md`: CLI state, warning, and compatibility contract.
- `docs/skills.md`: human-readable skill behavior.
- `README.md`: date-only import behavior and release pin.
- `pyproject.toml`, `uv.lock`, all three `skills/*/SKILL.md`: synchronized `0.2.1` release metadata.

---

### Task 1: Persist and Detect Approximate History Boundaries

**Files:**
- Modify: `weekly_report/report_file_manager.py:1-150`
- Modify: `tests/unit/test_report_file_manager.py:1-195`

**Interfaces:**
- Consumes: existing `Home`, report filename timestamps, and report text bookkeeping.
- Produces: `APPROXIMATE_BOUNDARY_MARKER: str`, `add_approximate_boundary_marker(text: str) -> str`, `has_approximate_boundary_marker(text: str) -> bool`, `import_report(..., approximate_boundary: bool = False) -> Path`, and `ReportFileManager.last_report_boundary() -> tuple[datetime, bool] | None`.

- [ ] **Step 1: Add failing marker and import tests**

Update the import list and add these tests to `tests/unit/test_report_file_manager.py`:

```python
from weekly_report.report_file_manager import (
    APPROXIMATE_BOUNDARY_MARKER,
    ReportFileManager,
    add_approximate_boundary_marker,
    blank_report_content,
    has_approximate_boundary_marker,
    import_report,
    is_blank_report_text,
    parse_created_marker,
    report_date,
    strip_report_marks,
)


class TestApproximateBoundaryMarker:
    def test_adds_marker_once_at_the_start(self):
        report = "# 7/30\n* worked\n"
        marked = add_approximate_boundary_marker(report)

        assert marked == f"{APPROXIMATE_BOUNDARY_MARKER}\n{report}"
        assert add_approximate_boundary_marker(marked) == marked
        assert has_approximate_boundary_marker(marked)

    def test_marker_must_be_the_first_line(self):
        text = f"# 7/30\n{APPROXIMATE_BOUNDARY_MARKER}\n"
        assert not has_approximate_boundary_marker(text)


```

Append this method to the existing `TestStripReportMarks` class:

```python
def test_removes_approximate_boundary_marker(self):
    text = f"{APPROXIMATE_BOUNDARY_MARKER}\n# 7/30\n* worked\n"
    assert strip_report_marks(text) == "# 7/30\n* worked"
```

Append this method to the existing `TestHistory` class:

```python
def test_import_report_can_mark_an_approximate_boundary(self, home, tmp_path):
    source = tmp_path / "old.md"
    source.write_text("# 7/30\n* worked\n", encoding="utf-8")

    destination = import_report(
        home,
        source,
        datetime(2026, 7, 30),
        approximate_boundary=True,
    )

    assert destination.name == "report-20260730-000000.md"
    assert destination.read_text(encoding="utf-8") == (
        f"{APPROXIMATE_BOUNDARY_MARKER}\n# 7/30\n* worked\n"
    )
    assert source.read_text(encoding="utf-8") == "# 7/30\n* worked\n"
```

- [ ] **Step 2: Run the marker tests and verify they fail**

Run:

```bash
uv run --isolated pytest \
  tests/unit/test_report_file_manager.py::TestApproximateBoundaryMarker \
  tests/unit/test_report_file_manager.py::TestStripReportMarks::test_removes_approximate_boundary_marker \
  tests/unit/test_report_file_manager.py::TestHistory::test_import_report_can_mark_an_approximate_boundary -q
```

Expected: collection errors for missing marker names or `TypeError` for the missing `approximate_boundary` argument.

- [ ] **Step 3: Implement marker persistence and stripping**

In `weekly_report/report_file_manager.py`, remove the now-unused `shutil` import and add:

```python
APPROXIMATE_BOUNDARY_MARKER = "[//]: # (weekly-report: boundary approximate date-only)"


def has_approximate_boundary_marker(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and lines[0] == APPROXIMATE_BOUNDARY_MARKER


def add_approximate_boundary_marker(text: str) -> str:
    if has_approximate_boundary_marker(text):
        return text
    return f"{APPROXIMATE_BOUNDARY_MARKER}\n{text}"
```

Extend `strip_report_marks` so the bookkeeping marker is filtered with the existing created marker and blank placeholder:

```python
lines = [
    line
    for line in text.splitlines()
    if not _CREATED_MARKER_RE.search(line)
    and line.rstrip() != REPORT_BLANK_MESSAGE
    and line.rstrip() != APPROXIMATE_BOUNDARY_MARKER
]
```

Change `import_report` without changing its default behavior:

```python
def import_report(home: Home, source: Path, date: datetime, *, approximate_boundary: bool = False) -> Path:
    """Copy an existing report into history/ under the given date."""
    home.ensure()
    destination = home.history_dir / f"report-{date.strftime(REPORT_FILENAME_FORMAT)}.md"
    if destination.exists():
        raise FileExistsError(f"already in history: {destination}")
    text = source.read_text(encoding="utf-8")
    if approximate_boundary:
        text = add_approximate_boundary_marker(text)
    destination.write_text(text, encoding="utf-8")
    return destination
```

Constructing the complete marked text before `write_text` ensures the implementation never deliberately copies an unmarked approximate report.

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
uv run --isolated pytest tests/unit/test_report_file_manager.py -q
```

Expected: every test in `test_report_file_manager.py` passes, including the existing exact-copy test.

- [ ] **Step 5: Add failing latest-boundary metadata tests**

Add the following to `TestKnownReports`:

```python
def test_last_report_boundary_marks_imported_history_as_approximate(self, home):
    date = datetime(2026, 7, 30)
    (path,) = write_history(home, date, content="# 7/30\n* worked")
    path.write_text(add_approximate_boundary_marker(path.read_text(encoding="utf-8")), encoding="utf-8")

    manager = ReportFileManager(home, history_limit=5)

    assert manager.last_report_boundary() == (date, True)
    assert manager.last_report_date() == date


def test_exact_report_md_supersedes_approximate_history(self, home):
    (path,) = write_history(home, datetime(2026, 7, 30), content="# 7/30\n* worked")
    path.write_text(add_approximate_boundary_marker(path.read_text(encoding="utf-8")), encoding="utf-8")
    manager = ReportFileManager(home, history_limit=5)
    exact = datetime(2026, 8, 6, 9, 38, 3)
    manager.create_blank_report(created=exact)
    with home.report_path.open("a", encoding="utf-8") as report:
        report.write("# 8/6\n* worked\n")

    assert manager.last_report_boundary() == (exact, False)
    assert manager.last_report_date() == exact
```

- [ ] **Step 6: Run the boundary tests and verify they fail**

Run:

```bash
uv run --isolated pytest \
  tests/unit/test_report_file_manager.py::TestKnownReports::test_last_report_boundary_marks_imported_history_as_approximate \
  tests/unit/test_report_file_manager.py::TestKnownReports::test_exact_report_md_supersedes_approximate_history -q
```

Expected: FAIL with `AttributeError: 'ReportFileManager' object has no attribute 'last_report_boundary'`.

- [ ] **Step 7: Implement latest-boundary metadata**

Add this method and make `last_report_date` delegate to it:

```python
def last_report_boundary(self) -> tuple[datetime, bool] | None:
    entries = self.known_reports()
    if not entries:
        return None
    date, path = entries[0]
    text = path.read_text(encoding="utf-8")
    return date, has_approximate_boundary_marker(text)

def last_report_date(self) -> datetime | None:
    boundary = self.last_report_boundary()
    return boundary[0] if boundary else None
```

- [ ] **Step 8: Run all report manager tests**

Run:

```bash
uv run --isolated pytest tests/unit/test_report_file_manager.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add weekly_report/report_file_manager.py tests/unit/test_report_file_manager.py
git commit -m "feat: track approximate history boundaries"
```

---

### Task 2: Use Midnight and Warn Until an Exact Boundary Exists

**Files:**
- Modify: `weekly_report/main.py:40-250,468-509`
- Modify: `tests/integration/test_main_cli.py:1-340`

**Interfaces:**
- Consumes: `ReportFileManager.last_report_boundary()` and `import_report(..., approximate_boundary=True)` from Task 1.
- Produces: `_approximate_boundary_warning(date: datetime) -> str`, midnight history filenames, and canonical English warnings from both `history import --json` and `run --json`.

- [ ] **Step 1: Update import tests to specify midnight and the canonical warning**

In `TestHistoryImport`, change the existing expected names and dates from `090000`/`T09:00:00` to `000000`/`T00:00:00`. Add:

```python
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
```

- [ ] **Step 2: Run import tests and verify they fail**

Run:

```bash
uv run --isolated pytest tests/integration/test_main_cli.py::TestHistoryImport -q
```

Expected: failures showing `09:00:00` instead of midnight, missing marker, and an empty warning list.

- [ ] **Step 3: Add the canonical warning helper and midnight import**

Add near `_iso` in `weekly_report/main.py`:

```python
def _approximate_boundary_warning(date: datetime) -> str:
    return (
        "Onboarding only knows the imported report's date, not its exact cutoff time. "
        f"To avoid missing commits, the first collection includes the entire boundary day ({date:%Y-%m-%d}). "
        "Some work may overlap with the imported report, so please review the generated draft for duplicate items."
    )
```

Change `cmd_history_import` to normalize every date to midnight, mark every imported report, and return one warning for the newest date:

```python
for index, source in enumerate(sources):
    date = first_date - timedelta(days=7 * index)
    date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    destination = import_report(home, source, date, approximate_boundary=True)
    imported.append({"source": str(source), "path": str(destination), "date": _iso(date)})

warnings = [_approximate_boundary_warning(first_date)]
payload = {"schema_version": SCHEMA_VERSION, "status": "ok", "imported": imported, "warnings": warnings}
```

Remove the obsolete comment that calls `09:00` arbitrary.

- [ ] **Step 4: Run import tests and verify they pass**

Run:

```bash
uv run --isolated pytest tests/integration/test_main_cli.py::TestHistoryImport -q
```

Expected: PASS.

- [ ] **Step 5: Add failing run-lifecycle tests**

Import `timedelta` in `tests/integration/test_main_cli.py` and add these tests to `TestRun`:

```python
def test_approximate_boundary_warning_survives_dry_run(self, home, tmp_path, make_repo, commit_in, capsys):
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


def test_exact_written_report_clears_approximate_warning(self, home, tmp_path, make_repo, commit_in, capsys):
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


def test_no_commits_does_not_consume_approximate_warning(self, home, tmp_path, make_repo, commit_in, capsys):
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
    assert any("first collection includes the entire boundary day" in warning for warning in no_commit["warnings"])
    assert retry_exit == 0
    assert any("first collection includes the entire boundary day" in warning for warning in retry["warnings"])
```

- [ ] **Step 6: Run the lifecycle tests and verify they fail**

Run:

```bash
uv run --isolated pytest \
  tests/integration/test_main_cli.py::TestRun::test_approximate_boundary_warning_survives_dry_run \
  tests/integration/test_main_cli.py::TestRun::test_exact_written_report_clears_approximate_warning \
  tests/integration/test_main_cli.py::TestRun::test_no_commits_does_not_consume_approximate_warning -q
```

Expected: warnings are missing because `cmd_run` still uses only `last_report_date()`.

- [ ] **Step 7: Emit the warning while the latest boundary is approximate**

Replace the existing last-report lookup in `cmd_run` with:

```python
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
```

Keep `last_report_date` available for the existing `history_info` payload. Do not add a new JSON field.

- [ ] **Step 8: Run CLI integration tests**

Run:

```bash
uv run --isolated pytest tests/integration/test_main_cli.py -q
```

Expected: PASS, including markerless history and normal exact-cycle tests.

- [ ] **Step 9: Commit Task 2**

```bash
git add weekly_report/main.py tests/integration/test_main_cli.py
git commit -m "fix: avoid gaps at imported report boundaries"
```

---

### Task 3: Localize Warnings in Skills and Document the Contract

**Files:**
- Modify: `skills/weekly-report/SKILL.md:20-40`
- Modify: `skills/weekly-report-onboard/SKILL.md:90-125`
- Create: `tests/unit/test_skill_warning_contract.py`
- Modify: `docs/contract.md:55-105,150-158`
- Modify: `docs/skills.md:20-140`
- Modify: `README.md:30-55`

**Interfaces:**
- Consumes: canonical English strings from Task 2's `warnings` arrays.
- Produces: a stable agent contract that translates warnings at presentation time and repeats approximate-boundary warnings in final handoffs.

- [ ] **Step 1: Add failing static skill-contract tests**

Create `tests/unit/test_skill_warning_contract.py`:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def skill_text(name: str) -> str:
    return (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_user_facing_skills_translate_canonical_english_warnings():
    for name in ("weekly-report", "weekly-report-onboard"):
        text = skill_text(name)
        assert "canonical English" in text
        assert "language of the user's latest request" in text
        assert "dates, file paths, commands, and technical identifiers" in text
        assert "If the request language is unclear, use the original English warning" in text


def test_weekly_report_repeats_approximate_warning_in_final_handoff():
    text = skill_text("weekly-report")
    assert "Repeat an approximate-boundary warning in the final response" in text


def test_onboarding_import_examples_request_json():
    text = skill_text("weekly-report-onboard")
    assert "--weekly-from 2026-07-23 --json" in text
    assert "history import" in text
```

- [ ] **Step 2: Run the skill-contract tests and verify they fail**

Run:

```bash
uv run --isolated pytest tests/unit/test_skill_warning_contract.py -q
```

Expected: FAIL because the localization instructions and JSON import example do not exist.

- [ ] **Step 3: Update `weekly-report` warning handling**

Replace the current “relay warnings as-is” instruction with this exact policy:

```markdown
5. CLI warnings are canonical English. Before showing them to the user, translate each warning into the language of the user's latest request. Preserve dates, file paths, commands, and technical identifiers verbatim. If the request language is unclear, use the original English warning.
```

Add to the final handoff requirements:

```markdown
- Repeat an approximate-boundary warning in the final response after writing the report, so it remains visible when commentary is collapsed. Tell the user to review the generated draft for duplicate items.
```

Do not paste the report body into the conversation.

- [ ] **Step 4: Update onboarding import and warning handling**

In `skills/weekly-report-onboard/SKILL.md`:

- Add the same canonical-English translation policy.
- Add `--json` to the `history import ... --weekly-from` example and to the per-file `--date` instruction.
- Explain that date-only imports intentionally start at midnight to avoid omissions.
- Treat the approximate-boundary warning during import and dry-run as expected, not as onboarding failure.
- Include the translated overlap warning in the final onboarding summary.

Use this instruction text so the static test has a stable contract:

```markdown
CLI warnings are canonical English. Translate them into the language of the user's latest request before presenting them. Preserve dates, file paths, commands, and technical identifiers verbatim. If the request language is unclear, use the original English warning.
```

- [ ] **Step 5: Run skill-contract tests and verify they pass**

Run:

```bash
uv run --isolated pytest tests/unit/test_skill_warning_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Update user and CLI documentation**

Update `docs/contract.md` to specify:

- Imported date-only boundaries are saved at `00:00:00`.
- Imported reports carry the approximate marker, which is stripped from prompts.
- Import and the first run return the canonical English warning.
- Dry-run/no-commit runs do not consume the warning.
- A filled exact report suppresses future approximate warnings.
- CLI warnings stay English; user-facing skills translate them.

Update `docs/skills.md` so its steps match both runtime SKILL files. Update `README.md` with one concise note under State or CLI: the first collection after onboarding may overlap the imported report but will not omit boundary-day commits.

- [ ] **Step 7: Run documentation and unit checks**

Run:

```bash
git diff --check
uv run --isolated pytest tests/unit/test_skill_warning_contract.py tests/unit/test_report_file_manager.py -q
```

Expected: no whitespace errors and all selected tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add \
  skills/weekly-report/SKILL.md \
  skills/weekly-report-onboard/SKILL.md \
  tests/unit/test_skill_warning_contract.py \
  docs/contract.md \
  docs/skills.md \
  README.md
git commit -m "docs: localize onboarding boundary warnings"
```

---

### Task 4: Synchronize the `0.2.1` Release and Verify the Repository

**Files:**
- Modify: `pyproject.toml:1-6`
- Modify: `uv.lock`
- Modify: `skills/weekly-report/SKILL.md`
- Modify: `skills/weekly-report-onboard/SKILL.md`
- Modify: `skills/weekly-report-repos/SKILL.md`
- Modify: `README.md:15-25`
- Modify: `docs/contract.md:170-180`
- Test: `tests/unit/test_version_sync.py`

**Interfaces:**
- Consumes: all completed behavior and documentation from Tasks 1-3.
- Produces: a repository consistently pinned to the future `v0.2.1` Git tag. Tag creation and pushing remain a separate release action.

- [ ] **Step 1: Bump package and skill pins to `0.2.1`**

Change:

```toml
[project]
name = "weekly-report"
version = "0.2.1"
```

Replace `@v0.2.0` with `@v0.2.1` in all three runtime `SKILL.md` files, `README.md`, and the executable example in `docs/contract.md`. Do not rewrite historical references in `docs/decisions.md` or `docs/migration.md`.

- [ ] **Step 2: Refresh the lock file**

Run:

```bash
uv lock
```

Expected: the local `weekly-report` package entry in `uv.lock` changes to `version = "0.2.1"` without unrelated dependency upgrades.

- [ ] **Step 3: Run version synchronization tests**

Run:

```bash
uv run --isolated pytest tests/unit/test_version_sync.py -q
```

Expected: all skill and README pins match `pyproject.toml` version `0.2.1`.

- [ ] **Step 4: Run the complete test suite**

Run:

```bash
uv run --isolated pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Run lint and type checks**

Run:

```bash
uv run --isolated ruff check .
uv run --isolated pyright
git diff --check
```

Expected: Ruff reports no violations, Pyright reports zero errors, and Git reports no whitespace errors.

- [ ] **Step 6: Inspect the final diff and preserve unrelated work**

Run:

```bash
git status --short
git diff --stat HEAD~3
git diff -- . ':(exclude).gitignore'
```

Expected: only the files listed in this plan are changed by the implementation. `.gitignore` remains modified but unstaged and untouched.

- [ ] **Step 7: Commit release metadata**

```bash
git add \
  pyproject.toml \
  uv.lock \
  skills/weekly-report/SKILL.md \
  skills/weekly-report-onboard/SKILL.md \
  skills/weekly-report-repos/SKILL.md \
  README.md \
  docs/contract.md
git commit -m "chore: prepare v0.2.1"
```

- [ ] **Step 8: Record final verification evidence**

Run:

```bash
git status --short
git log -5 --oneline
uv run --isolated pytest -q
uv run --isolated ruff check .
uv run --isolated pyright
```

Expected: only the pre-existing `.gitignore` modification remains, the implementation commits are visible, and every verification command passes. Do not create or push `v0.2.1` without explicit release authorization.

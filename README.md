# weekly-report

> **Note**: This is a personal project designed for individual use.

Weekly development reports from Git history, driven by agent skills. The CLI collects
commits and builds a prompt file; an agent skill reads it, writes the report draft, and
hands you the file to polish.

## Install

Two pieces share this repository and are pinned to the same git tag:

```
npx skills add mjkimR/weekly-report        # installs the skills into your agent
```

The skills run the CLI straight from git — no separate install, only [uv](https://docs.astral.sh/uv/) is required:

```
uvx --from git+https://github.com/mjkimR/weekly-report@v0.2.0 weekly-report <command>
```

## Skills

| Skill | Use |
| --- | --- |
| `weekly-report` | Write this week's report. The only skill used routinely |
| `weekly-report-onboard` | First-time setup: infer the format from past reports, pick repositories and authors, seed history |
| `weekly-report-repos` | List, add or remove target repositories |

## CLI

```
weekly-report run [--json] [--dry-run]                # collect commits, write prompt.md + blank report.md
weekly-report repo list|add|remove [...]              # manage target repositories
weekly-report authors <path>... [--json]              # commit-author candidates per repository
weekly-report history import <file>... --date|--weekly-from <YYYY-MM-DD>
```

The JSON shapes, exit codes and file layout are specified in [docs/contract.md](docs/contract.md).
Exit codes: `0` ok, `1` no commits in the period (nothing written), `2` not configured,
`3` repository unreadable.

## State

Everything lives under `~/.weekly-report/` (override with `WEEKLY_REPORT_HOME`):

- `config.yaml` — settings; created by onboarding, edited by hand or via `repo` commands
- `template.md` — report format; created by onboarding
- `report.md` — this week's working file; a new blank one is created each run
- `prompt.md` — intermediate artifact, overwritten every run
- `history/` — archived reports; the newest one decides the next collection window

`history/` is the tool's only persistent state and is not tracked by Git — so it is not
backed up either.

Date-only onboarding starts the first collection at `00:00:00` on the imported report's date. This guarantees that boundary-day commits are not omitted, but the first generated draft may overlap the imported report and should be checked for duplicate items.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `author` | — | Global commit author name; `repository[].authors` overrides per repo |
| `repository` | `[]` | Objects with `path`, optional `name` and `authors` |
| `lang` | `english` | Language the report is written in |
| `max_diff_lines` | `50` | Diff lines shown per commit before truncation (`0` omits diffs) |
| `report_history_limit` | `5` | Reports kept in `history/` and fed to the prompt (min `1`) |
| `large_prompt_tokens` | `150000` | Warn above this estimated token count (advisory only) |

Constraint rationale lives as comments in `weekly_report/schemas.py`; design decisions in
[docs/decisions.md](docs/decisions.md).

## Development

```
uv run pytest                       # everything
uv run pytest -m "not integration"  # skip the tests that shell out to git
uv run ruff check .                 # lint
uv run pyright                      # type check
```

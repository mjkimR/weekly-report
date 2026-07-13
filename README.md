# Weekly Report Prompt Generator

> **Note**: This is a personal project designed for individual use. 

This tool generates structured prompts for LLM to create weekly development reports based on Git commit data.

## Purpose

This project doesn't generate the actual weekly reports directly. Instead, it:
1. Collects Git commit data from specified repositories
2. Processes and structures the data
3. Generates a comprehensive prompt for LLM (Large Language Model)
4. Creates a template file that can be used with the LLM to generate the actual weekly report

## Features

- Collects commit data from multiple Git repositories
- Tracks changes since the last report
- Generates structured prompts for LLM consumption
- Maintains report history
- Configurable templates and settings

## Usage

1. Run `uv run python setup_conf.py` once to create `config/config.yaml` and `config/template.md` from the examples
2. Configure your repositories and settings in `config/config.yaml`
3. Run `uv run weekly-report-prompt` to generate the prompt
4. Use the generated prompt with your preferred LLM to create the actual report
5. Paste the report into `build/report-<timestamp>.md`; the next run archives it and uses it as the starting point

```
uv run weekly-report-prompt [--dry-run] [--config PATH] [--template PATH] [--build-dir PATH]
```

Use `--dry-run` to see the summary and token count without writing anything to the build
directory. A run that finds no commits exits non-zero and leaves the build directory alone.

### Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `author` | — | Only commits by this author name are collected |
| `repository` | `[]` | Paths of the Git repositories to read |
| `lang` | `ko` | Language the LLM should write the report in |
| `max_diff_lines` | `25` | Diff lines shown per commit before truncation (`0` omits diffs) |
| `report_history_limit` | `10` | Reports kept in `build/history` and fed to the prompt (min `1`) |
| `large_prompt_tokens` | `150000` | Warn above this token count |

`report_history_limit` also decides what is deleted from the archive, so it is rejected
below `1` — a `0` would empty `build/history`, and nothing else records which periods you
have already reported on.

The `large_prompt_tokens` warning is advisory; nothing is truncated and the run still
succeeds. Raise it if you paste the prompt into a model with a large context window —
Gemini and GPT fit roughly 1M tokens, Claude roughly 200k.

## Development

```
uv run pytest                       # everything
uv run pytest -m "not integration"  # skip the tests that shell out to git
uv run ruff check .                 # lint
uv run pyright                      # type check
```

## Output

The tool writes into `build/`:
- `prompt-<timestamp>.md` — the prompt to paste into an LLM
- `report-<timestamp>.md` — a blank report for you to fill in with the LLM's answer
- `memo.md` — free-form notes carried into the next prompt
- `history/` — reports you filled in on previous runs

`build/` is the tool's only persistent state. The archive under `history/` is what decides
the next run's collection window, and it is not tracked by Git — so it is not backed up
either.

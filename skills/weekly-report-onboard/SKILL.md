---
name: weekly-report-onboard
description: First-time setup for the weekly report skill. Takes a few past reports to infer the format and language, then picks target repositories and authors. Use for "주간보고 설정", "온보딩", or when starting to use the weekly report for the first time.
---

# weekly-report-onboard

Sets up the weekly report for the first time: reverse-engineer the format and tone from past reports, then create the config, template, and history. Onboarding does not produce a report.

All CLI calls run as:

```
uvx --from git+https://github.com/mjkimR/weekly-report@v0.2.1 weekly-report <command>
```

## Steps

1. Check for uv with `command -v uv`. If missing, point to the installer (https://docs.astral.sh/uv/getting-started/installation/) and stop.
2. Probe the current state with `weekly-report run --json`. If the exit code is not 2, configuration already exists — ask whether to overwrite, and stop if not. `paths.home` in the JSON is where the configuration goes (default `~/.weekly-report/`).
3. Collect past reports. Pasted text and file paths both work. Suggest 2 to 5 as the useful range. With none, start from the default template below.
4. Extract the format using the checklist.
5. Show a draft `template.md` and get it confirmed. Then write it to `<home>/template.md`.
6. Choose the target repositories.
7. Settle the authors with `weekly-report authors <path>... --json`.
8. Write `<home>/config.yaml`.
9. Seed the received reports with `weekly-report history import`.
10. Verify with `weekly-report run --dry-run --json`.

CLI warnings are canonical English. Translate them into the language of the user's latest request before presenting them. Preserve dates, file paths, commands, and technical identifiers verbatim. If the request language is unclear, use the original English warning.

## Step 4: format checklist

Extract the following from the received reports. Anything guessed gets confirmed with the user in step 5.

| Item | What to look at | Example |
| --- | --- | --- |
| Language | Language of the body text | `korean` |
| Title format | Date notation on the first line | `# 7/23`, `# 2026/07/23`, `# 2026-07-23 주간보고` |
| Section headings | Top-level headings and their order | `## 한 일`, `## 할 일` |
| Nesting depth | How deep the lists go | 4 levels (category → subcategory → item → detail) |
| Grouping axis | What splits the top-level items | by repository, by work area, or a mix |
| Sentence style | How items end | noun-ending, full sentences, terse bullet style |
| Item length | Typical characters per item | 30–80 chars |
| Parenthesis habit | How asides are attached | `기능 추가 (호환성 대응)` |

`template.md` uses placeholders (`{main_category_1}`, `{item_1}`), not real content. Nesting depth and section headings are the core of the format; tone and item length come from the past reports embedded in the prompt.

Getting the grouping axis wrong shows every single week. With several repositories, a report grouped by repository reads completely differently from one grouped by work area — always get this item confirmed.

Default template (when no past reports were given):

```text
# {date:YYYY/M/D}

## Work Done

* {main_category_1}
    * {sub_category_1}
        * {item_1}
            * {detail_1}

## Next Tasks

* {next_task_1}
```

## Step 6: target repositories

If the current working directory is a Git repository, propose it as a candidate. Never add it without confirmation — the skill may be installed globally and run from any project, and adding automatically would mix someone else's repository into the report.

Then ask for other repository paths; several are typical. Propose the last path segment as the default display name, noting that the name appears verbatim in the report.

## Step 7: authors

Show the `weekly-report authors` output. Commit author names can differ per repository, and `git_user_name` can disagree with the actual commit names. This step is where that gets caught.

If every repository uses the same name, a single global `author` is enough. Attach a per-repository `authors` list only to the repositories that differ.

## Step 8: config.yaml

```yaml
author: minjae.kim            # Global default author
lang: korean                  # Language the report is written in; goes into the prompt verbatim

repository:
  - path: /Users/mj/workspace/athena
    name: Athena              # Optional; defaults to the last path segment
    authors: [minjae.kim]     # Optional; defaults to the global author alone

max_diff_lines: 50            # Diff lines per commit; 0 omits diffs
report_history_limit: 5       # Reports kept in history/ and fed to the prompt; min 1
large_prompt_tokens: 150000   # Above this, warn only
```

## Step 9: seeding history

**Skipping this step leaves onboarding unfinished.** `history/` is the only record that decides where the next collection window starts; if it is empty, the first run falls back to the last 7 days.

Ask the user for the dates. Never guess them from file contents — report titles often lack a year, and a wrong date silently skews the next collection window.

Asking only for the newest report's date and stepping back 7 days for the rest is enough:

```
weekly-report history import newest.md previous.md before-that.md --weekly-from 2026-07-23 --json
```

If the user says the cadence was irregular, import one file at a time with `weekly-report history import report.md --date 2026-07-23 --json`. Save pasted reports to temporary files before importing.

An imported date has no exact cutoff time. The CLI deliberately records it as `00:00:00` and includes the whole boundary day in the first collection so no commits can be omitted. The import and verification dry-run therefore return an approximate-boundary warning; this is expected and does not mean onboarding failed. Translate that warning before presenting it.

## Step 10: verification

Run `weekly-report run --dry-run --json` and check:

- `period.since_source` is `history`. If it is `fallback_7d`, step 9 went wrong
- `period.since` matches the newest report's date
- Per-repository commit counts are non-zero. Zero usually means the author name is wrong
- The token estimate is under the threshold. If over, advise lowering `max_diff_lines`

Finish by telling the user the config file and state directory paths, and that from now on the `weekly-report` skill is the one to use. Include the translated approximate-boundary warning in this final summary and tell the user to review the first generated draft for duplicate items.

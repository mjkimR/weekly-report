---
name: weekly-report
description: Write this week's weekly report. Collects Git commits into a draft and hands the user a file to edit. Use for requests like "주간보고", "주간 리포트", "weekly report", or "summarize what I did this week".
---

# weekly-report

Handles one weekly report. The CLI collects commits and builds a prompt file; this skill writes the report from that prompt and delivers it as a file.

## Steps

1. Check for uv with `command -v uv`. If missing, point to the installer (https://docs.astral.sh/uv/getting-started/installation/) and stop.
2. Run the command below. Never run it twice — a second run deletes the blank report.md it just created and recomputes the collection window.

   ```
   uvx --from git+https://github.com/mjkimR/weekly-report@v0.2.0 weekly-report run --json
   ```

3. If the exit code is not 0, stop here:
   - 1 (`no_commits`): there were no commits this week — a fact, not a failure. Tell the user. Files are untouched.
   - 2 (`not_configured`): point the user to the `weekly-report-onboard` skill.
   - 3 (`repo_error`): report the failing path from `warnings` and point to the `weekly-report-repos` skill.
4. If `period.since_source` is `fallback_7d`, no previous report was found and the window defaulted to the last 7 days. Ask the user whether that window is right before continuing.
5. CLI warnings are canonical English. Before showing them to the user, translate each warning into the language of the user's latest request. Preserve dates, file paths, commands, and technical identifiers verbatim. If the request language is unclear, use the original English warning.
6. Read the file at `paths.prompt`.
7. Write the report following the prompt's instructions. The format comes from the template inside the prompt; tone, item length, and phrasing come from the past reports included in the prompt. If the user mentioned anything extra when invoking the skill (meetings, documentation work, things commits don't show), incorporate it.
8. Write the report to the file at `paths.report` and nowhere else. Keep the first line — the `[//]: # (weekly-report: created ...)` comment — exactly as-is and write below it; the next run uses it to continue the collection window.
9. Tell the user:
   - A one-line summary of the collection window and per-repository commit counts
   - The absolute path of `paths.report` (the user opens and edits it)
   - The token estimate only if `tokens.over_threshold` is true, noting it is a rough estimate (`len//4`)
   - Repeat an approximate-boundary warning in the final response after writing the report, so it remains visible when commentary is collapsed. Tell the user to review the generated draft for duplicate items.

## Cautions

- Do not paste the report body into the conversation. The user opens the file to read and edit it.
- `run` has already archived the previous report and created a blank report.md. Do not redo that housekeeping.
- The prompt already contains the past reports; do not read them separately.
- Do not edit the config file to work around problems. Route configuration issues to `weekly-report-onboard` / `weekly-report-repos`.

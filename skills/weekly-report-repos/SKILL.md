---
name: weekly-report-repos
description: Manage the list of Git repositories the weekly report covers. Use when adding or removing a repository or checking the current list, e.g. "주간보고 저장소 추가/제거/목록".
---

# weekly-report-repos

View, add, or remove the repositories the weekly report covers.

Check for uv first with `command -v uv`. If missing, point to the installer (https://docs.astral.sh/uv/getting-started/installation/) and stop.

Read what the user wants from their message and call the matching command. All commands run as:

```
uvx --from git+https://github.com/mjkimR/weekly-report@v0.2.0 weekly-report repo <subcommand>
```

| Request | Command |
| --- | --- |
| Show the list | `repo list --json` |
| Add | `repo add <path> [--name <display name>] [--author <name>]...` |
| Remove | `repo remove <name-or-path>` |

Exit code 2 means there is no configuration yet — point to `weekly-report-onboard`. Exit code 3 means the path is not a Git repository.

## When adding

- If no path was given, propose the current directory as a candidate and get confirmation. Never add without confirmation.
- If a subdirectory was given, the CLI finds and stores the repository root. If `warnings` shows the actually stored path, tell the user.
- If the CLI warns "no commits by ...", relay it and offer to check author names with `weekly-report authors <path>`. Skipping this leads to silent zero-commit weeks.
- Tell the user the display name (`--name`) appears verbatim in the report.

## When removing

- Confirm what was removed. If `removed` is null, that name was not registered in the first place.
- `history/` is never touched. Past reports still mentioning the removed repository is normal.

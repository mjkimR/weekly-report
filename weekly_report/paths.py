"""Where configuration and state live.

Everything sits under one directory -- default ``~/.weekly-report``, overridable with
``WEEKLY_REPORT_HOME`` -- so there is exactly one place to remember. Keeping it outside
any project tree means skill installs never leak artifacts into a repository.
"""

import os
from pathlib import Path

ENV_HOME = "WEEKLY_REPORT_HOME"
DEFAULT_HOME = "~/.weekly-report"


class Home:
    def __init__(self, root: str | Path | None = None):
        if root is None:
            root = os.environ.get(ENV_HOME) or DEFAULT_HOME
        self.root = Path(root).expanduser()

    @property
    def config_path(self) -> Path:
        return self.root / "config.yaml"

    @property
    def template_path(self) -> Path:
        return self.root / "template.md"

    @property
    def report_path(self) -> Path:
        return self.root / "report.md"

    @property
    def prompt_path(self) -> Path:
        return self.root / "prompt.md"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    def ensure(self) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)

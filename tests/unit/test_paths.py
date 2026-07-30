from pathlib import Path

from weekly_report.paths import DEFAULT_HOME, ENV_HOME, Home


class TestHome:
    def test_env_variable_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ENV_HOME, str(tmp_path / "elsewhere"))
        assert Home().root == tmp_path / "elsewhere"

    def test_default_is_dot_weekly_report_in_home(self, monkeypatch):
        monkeypatch.delenv(ENV_HOME, raising=False)
        assert Home().root == Path(DEFAULT_HOME).expanduser()

    def test_known_file_layout(self, tmp_path):
        home = Home(tmp_path)
        assert home.config_path == tmp_path / "config.yaml"
        assert home.template_path == tmp_path / "template.md"
        assert home.report_path == tmp_path / "report.md"
        assert home.prompt_path == tmp_path / "prompt.md"
        assert home.history_dir == tmp_path / "history"

    def test_ensure_creates_root_and_history(self, tmp_path):
        home = Home(tmp_path / "new-home")
        home.ensure()
        assert home.history_dir.is_dir()

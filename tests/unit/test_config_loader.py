import pytest

from weekly_report.config_loader import ConfigError, load_config, load_template, save_config
from weekly_report.schemas import AppConfig, RepositoryEntry


class TestLoadConfig:
    def test_missing_file(self, home):
        with pytest.raises(ConfigError, match="config not found"):
            load_config(home)

    def test_invalid_yaml(self, home):
        home.root.mkdir(parents=True)
        home.config_path.write_text("author: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigError, match="not valid YAML"):
            load_config(home)

    def test_invalid_schema(self, home):
        home.root.mkdir(parents=True)
        home.config_path.write_text("author: a\nreport_history_limit: 0\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="config is invalid"):
            load_config(home)

    def test_roundtrip(self, home):
        config = AppConfig(
            author="minjae.kim",
            lang="korean",
            repository=[RepositoryEntry(path="/work/athena", name="Athena")],
        )
        save_config(home, config)
        loaded = load_config(home)
        assert loaded == config

    def test_save_omits_unset_optionals(self, home):
        save_config(home, AppConfig(author="a", repository=[RepositoryEntry(path="/r")]))
        text = home.config_path.read_text(encoding="utf-8")
        assert "name:" not in text
        assert "authors:" not in text


class TestLoadTemplate:
    def test_missing_template(self, home):
        with pytest.raises(ConfigError, match="template not found"):
            load_template(home)

    def test_reads_contents(self, home):
        home.root.mkdir(parents=True)
        home.template_path.write_text("# {date}\n", encoding="utf-8")
        assert load_template(home) == "# {date}\n"

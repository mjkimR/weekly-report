import pytest
from pydantic import ValidationError

from weekly_report.schemas import AppConfig, RepositoryEntry


class TestRepositoryEntry:
    def test_display_name_defaults_to_last_path_segment(self):
        assert RepositoryEntry(path="/work/athena/").display_name() == "athena"

    def test_display_name_prefers_explicit_name(self):
        assert RepositoryEntry(path="/work/athena", name="Athena").display_name() == "Athena"

    def test_effective_authors_prefers_own_list(self):
        entry = RepositoryEntry(path="/r", authors=["mjkim"])
        assert entry.effective_authors("minjae.kim") == ["mjkim"]

    def test_effective_authors_falls_back_to_global(self):
        assert RepositoryEntry(path="/r").effective_authors("minjae.kim") == ["minjae.kim"]

    def test_effective_authors_empty_without_any(self):
        assert RepositoryEntry(path="/r").effective_authors(None) == []


class TestAppConfig:
    def test_full_v02_config(self):
        config = AppConfig.model_validate(
            {
                "author": "minjae.kim",
                "lang": "korean",
                "repository": [{"path": "/work/athena", "name": "Athena", "authors": ["minjae.kim", "mjkim"]}],
                "max_diff_lines": 50,
                "report_history_limit": 5,
                "large_prompt_tokens": 150_000,
            }
        )
        assert config.repository[0].display_name() == "Athena"

    def test_v01_string_repository_list_is_rejected(self):
        # The v0.1 format is not accepted; docs/migration.md covers the conversion.
        with pytest.raises(ValidationError):
            AppConfig.model_validate({"author": "a", "repository": ["/work/athena"]})

    def test_repository_without_any_author_is_rejected(self):
        with pytest.raises(ValidationError):
            AppConfig.model_validate({"repository": [{"path": "/work/athena"}]})

    def test_per_repo_authors_satisfy_missing_global_author(self):
        config = AppConfig.model_validate({"repository": [{"path": "/r", "authors": ["mjkim"]}]})
        assert config.author is None

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("max_diff_lines", -1),
            ("report_history_limit", 0),
            ("large_prompt_tokens", 0),
        ],
    )
    def test_constraint_violations_are_rejected(self, field, bad_value):
        with pytest.raises(ValidationError):
            AppConfig.model_validate({"author": "a", field: bad_value})

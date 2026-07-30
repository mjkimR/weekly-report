"""Load and save the configuration and template kept in the home directory."""

import yaml
from pydantic import ValidationError

from weekly_report.paths import Home
from weekly_report.schemas import AppConfig


class ConfigError(Exception):
    """Configuration or template missing or invalid -- exit code 2 territory."""


def load_config(home: Home) -> AppConfig:
    if not home.config_path.exists():
        raise ConfigError(f"config not found: {home.config_path} (run the weekly-report-onboard skill to create it)")

    try:
        raw = yaml.safe_load(home.config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"config is not valid YAML: {home.config_path} ({error})") from error

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"config is invalid: {home.config_path}\n{error}") from error


def save_config(home: Home, config: AppConfig) -> None:
    """Rewrite config.yaml from the model. Hand-written comments do not survive this."""
    home.root.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(exclude_none=True)
    home.config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_template(home: Home) -> str:
    if not home.template_path.exists():
        raise ConfigError(
            f"template not found: {home.template_path} (run the weekly-report-onboard skill to create it)"
        )
    return home.template_path.read_text(encoding="utf-8")

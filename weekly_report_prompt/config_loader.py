import os
from pathlib import Path

import yaml

from weekly_report_prompt.schemas import AppConfig


class ConfigLoader:
    def __init__(self, config_path=None, template_path=None):
        if config_path is None:
            config_path = os.path.join(Path(__file__).parent.parent, "config", "config.yaml")
        if template_path is None:
            template_path = os.path.join(Path(__file__).parent.parent, "config", "template.md")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, encoding="utf-8") as f:
            self.settings = AppConfig.model_validate(yaml.safe_load(f) or {})

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template file not found: {template_path}")
        with open(template_path, encoding="utf-8") as f:
            self.template = f.read()

    def get_author(self):
        return self.settings.author

    def get_repositories(self):
        return self.settings.repository

    def get_max_diff_lines(self):
        return self.settings.max_diff_lines

    def get_lang(self):
        return self.settings.lang

    def get_report_history_limit(self):
        return self.settings.report_history_limit

    def get_large_prompt_tokens(self):
        return self.settings.large_prompt_tokens

    def get_template(self):
        return self.template

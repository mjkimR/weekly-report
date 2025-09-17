import pytest
import os
import yaml

from weekly_report_prompt.config_loader import ConfigLoader


class TestConfigLoader:
    """Test cases for ConfigLoader class."""

    def test_config_loader_initialization(self, config_loader):
        """Test ConfigLoader initialization with valid files."""
        assert config_loader is not None
        assert config_loader.config is not None
        assert config_loader.template is not None

    def test_config_loader_with_missing_config_file(self, template_file):
        """Test ConfigLoader initialization with missing config file."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            ConfigLoader(config_path="/nonexistent/config.yaml", template_path=template_file)

    def test_config_loader_with_missing_template_file(self, config_file):
        """Test ConfigLoader initialization with missing template file."""
        with pytest.raises(FileNotFoundError, match="Template file not found"):
            ConfigLoader(config_path=config_file, template_path="/nonexistent/template.md")

    def test_get_method(self, config_loader):
        """Test the generic get method."""
        assert config_loader.get("author") == "Test Author"
        assert config_loader.get("nonexistent_key") is None
        assert config_loader.get("nonexistent_key", "default_value") == "default_value"

    def test_get_author(self, config_loader):
        """Test getting author from config."""
        assert config_loader.get_author() == "Test Author"

    def test_get_repositories(self, config_loader):
        """Test getting repositories from config."""
        repos = config_loader.get_repositories()
        assert len(repos) == 1
        assert repos[0]["name"] == "test-repo"
        assert repos[0]["path"] == "/path/to/repo"

    def test_get_max_diff_lines(self, config_loader):
        """Test getting max diff lines from config."""
        assert config_loader.get_max_diff_lines() == 25

    def test_get_max_diff_lines_default(self, temp_dir):
        """Test getting max diff lines with default value."""
        # Create config without max_diff_lines
        config_data = {"author": "Test Author"}
        config_dir = os.path.join(temp_dir, "config")
        os.makedirs(config_dir, exist_ok=True)

        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        template_path = os.path.join(config_dir, "template.md")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write("# Template")

        loader = ConfigLoader(config_path=config_path, template_path=template_path)
        assert loader.get_max_diff_lines() == 25  # Default value

    def test_get_lang(self, config_loader):
        """Test getting language from config."""
        assert config_loader.get_lang() == "ko"

    def test_get_lang_default(self, temp_dir):
        """Test getting language with default value."""
        # Create config without lang
        config_data = {"author": "Test Author"}
        config_dir = os.path.join(temp_dir, "config")
        os.makedirs(config_dir, exist_ok=True)

        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        template_path = os.path.join(config_dir, "template.md")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write("# Template")

        loader = ConfigLoader(config_path=config_path, template_path=template_path)
        assert loader.get_lang() == "ko"  # Default value

    def test_get_report_history_limit(self, config_loader):
        """Test getting report history limit from config."""
        assert config_loader.get_report_history_limit() == 10

    def test_get_report_history_limit_default(self, temp_dir):
        """Test getting report history limit with default value."""
        # Create config without report_history_limit
        config_data = {"author": "Test Author"}
        config_dir = os.path.join(temp_dir, "config")
        os.makedirs(config_dir, exist_ok=True)

        config_path = os.path.join(config_dir, "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f)

        template_path = os.path.join(config_dir, "template.md")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write("# Template")

        loader = ConfigLoader(config_path=config_path, template_path=template_path)
        assert loader.get_report_history_limit() == 10  # Default value

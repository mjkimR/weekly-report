"""The uvx tag pinned in each SKILL.md must match the package version.

Skills run code from the git tag embedded in their body, and pyproject.toml's version is
the single source of truth. Tagging a release without bumping those pins would ship
skills that silently keep running the previous version -- this test makes that mistake
fail before the tag exists.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_RE = re.compile(r"git\+https://github\.com/mjkimR/weekly-report@v(\d+\.\d+\.\d+)")

EXPECTED_SKILLS = {"weekly-report", "weekly-report-onboard", "weekly-report-repos"}


def project_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_skill_set_is_known():
    # A new skill must be added here so the pin check below covers it.
    found = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    assert found == EXPECTED_SKILLS


def test_every_skill_pins_the_current_version():
    version = project_version()
    for name in sorted(EXPECTED_SKILLS):
        skill = REPO_ROOT / "skills" / name / "SKILL.md"
        pins = PIN_RE.findall(skill.read_text(encoding="utf-8"))
        assert pins, f"{skill} has no pinned uvx command"
        assert set(pins) == {version}, f"{skill} pins {sorted(set(pins))}, pyproject.toml says {version}"


def test_readme_examples_pin_the_current_version():
    pins = PIN_RE.findall((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    assert pins, "README.md should show the pinned uvx command"
    assert set(pins) == {project_version()}

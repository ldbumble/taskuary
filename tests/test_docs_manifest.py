"""The docs footer version must track releases (issue #134)."""

import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    # tomllib is 3.11+; parse the one-liner with regex for 3.10 support.
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert match, "version not found in pyproject.toml"
    return match.group(1)


def test_manifest_version_matches_pyproject():
    manifest = json.loads((ROOT / "docs/site/manifest.json").read_text())
    assert manifest["version"] == _pyproject_version(), (
        manifest["version"],
        _pyproject_version(),
    )


def test_manifest_updated_is_a_date():
    manifest = json.loads((ROOT / "docs/site/manifest.json").read_text())
    datetime.date.fromisoformat(manifest["updated"])

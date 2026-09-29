"""The live-house snapshot fixture: shape and sanitization guards.

``tests/fixtures/house_snapshot/`` is a read-only capture of the real house
(see its README). Later phases rehearse migrations against it, so its shape
is pinned here, and every refresh must stay free of secrets and location.
"""

from __future__ import annotations

import json
import re

import pytest

from .house_replay import SNAPSHOT_DIR, load_windows

FILES = sorted(SNAPSHOT_DIR.glob("*.json"))


def _entries() -> list[dict]:
    return json.loads((SNAPSHOT_DIR / "config_entries.json").read_text())["entries"]


def test_entries_are_fifteen_windows_one_hub_three_disabled():
    roles = [entry["role"] for entry in _entries()]
    assert roles.count("window") == 15
    assert roles.count("hub") == 1
    assert roles.count("disabled_legacy") == 3
    assert len(roles) == 19


def test_every_window_has_one_cover_and_its_registry_rows():
    for window in load_windows():
        assert window.data["sensor_type"] == "cover_blind", window.title
        assert len(window.options["group"]) == 1, window.title
        assert window.registry_rows, f"{window.title}: no registry rows"
        for row in window.registry_rows:
            assert row["unique_id"].startswith(window.entry_id), row


def test_windows_carry_complete_options():
    """Loaded windows come from diagnostics, so unset keys are explicit None."""
    for entry in _entries():
        if entry["role"] == "window":
            assert "end_entity" in entry["options"], entry["title"]
            assert "presence_entity" in entry["options"], entry["title"]


FORBIDDEN_KEYS = re.compile(
    r'"(latitude|longitude|lat|lon|elevation_m|access_token|token|password|'
    r'api_key|ieee|connections|mac|ip_address)"\s*:'
)
FORBIDDEN_VALUES = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # e-mail
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),  # IPv4
    re.compile(r"(?i)(access_token|token=|bearer\s)"),
    re.compile(r"(?i)\b(?:[0-9a-f]{2}:){7}[0-9a-f]{2}\b"),  # zigbee IEEE
]


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_snapshot_file_is_sanitized(path):
    text = path.read_text()
    json.loads(text)  # valid JSON
    assert not FORBIDDEN_KEYS.search(text), FORBIDDEN_KEYS.search(text).group(0)
    for pattern in FORBIDDEN_VALUES:
        match = pattern.search(text)
        assert match is None, f"{path.name}: sensitive-looking {match.group(0)!r}"

"""Structural guard: the pure runtime components take no ``hass`` (P4).

The coordinator split moves decisions into small components that the
coordinator feeds (time as an argument, entity states through a reader).
Tests drive them with fakes and no Home Assistant, so they must neither
import ``homeassistant`` nor mention ``hass``.
"""

import ast
from pathlib import Path

import pytest

RUNTIME_DIR = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "adaptive_cover"
    / "runtime"
)
PURE_MODULES = [
    "command_tracker.py",
    "gates.py",
    "manual_detector.py",
    "override_tracker.py",
    "schedule.py",
    "shade_config.py",
]


def _hass_uses(source: str) -> list[str]:
    """Every homeassistant import and every ``hass`` name in ``source``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        found += [
            f"line {node.lineno}: imports {module}"
            for module in modules
            if module.split(".")[0] == "homeassistant"
        ]
        name = (
            getattr(node, "id", None)
            or getattr(node, "arg", None)
            or getattr(node, "attr", None)
        )
        if name == "hass":
            found.append(f"line {node.lineno}: hass")
    return found


@pytest.mark.parametrize("module", PURE_MODULES)
def test_module_has_no_hass(module):
    uses = _hass_uses((RUNTIME_DIR / module).read_text())
    assert not uses, f"{module} depends on Home Assistant:\n" + "\n".join(uses)


def test_guard_catches_each_form():
    sample = (
        "import homeassistant.util.dt\n"
        "from homeassistant.core import HomeAssistant\n"
        "def f(hass): ...\n"
        "x = self.hass\n"
        "y = hass\n"
        "ok = self.hassle\n"
    )
    assert len(_hass_uses(sample)) == 5

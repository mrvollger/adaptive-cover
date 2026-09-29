"""Structural guard: the settings resolver and lift stay pure (P5).

``resolve.py``, ``lift.py`` and ``shadow.py`` are tested without Home
Assistant, like ``engine/``: no ``homeassistant`` import, no ``hass``, and
no clock reads (the lift and every resolve are functions of their inputs
only).
"""

import ast
from pathlib import Path

import pytest

SETTINGS_DIR = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "adaptive_cover"
    / "settings"
)
PURE_MODULES = ["resolve.py", "lift.py", "shadow.py"]
CLOCK_CALLS = {"now", "utcnow", "today", "time", "monotonic"}
CLOCK_MODULES = {"datetime", "time"}


def _impurities(source: str) -> list[str]:
    """Every homeassistant import, ``hass`` name and clock read in ``source``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            root = module.split(".")[0]
            if root == "homeassistant" or root in CLOCK_MODULES:
                found.append(f"line {node.lineno}: imports {module}")
        name = (
            getattr(node, "id", None)
            or getattr(node, "arg", None)
            or getattr(node, "attr", None)
        )
        if name == "hass":
            found.append(f"line {node.lineno}: hass")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in CLOCK_CALLS:
                found.append(f"line {node.lineno}: calls .{node.func.attr}()")
    return found


@pytest.mark.parametrize("module", PURE_MODULES)
def test_module_is_pure(module):
    found = _impurities((SETTINGS_DIR / module).read_text())
    assert not found, f"settings/{module} is not pure:\n" + "\n".join(found)


def test_guard_catches_each_form():
    sample = (
        "import homeassistant.util.dt\n"
        "from homeassistant.core import HomeAssistant\n"
        "import datetime\n"
        "from time import monotonic\n"
        "def f(hass): ...\n"
        "x = self.hass\n"
        "y = dt.now()\n"
        "z = dt_util.utcnow()\n"
        "ok = self.hassle\n"
    )
    assert len(_impurities(sample)) == 8

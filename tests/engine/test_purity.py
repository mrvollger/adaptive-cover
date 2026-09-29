"""The engine must stay pure: no HA imports, no wall-clock reads.

Time, sun position, and climate readings enter as explicit inputs; if the
engine ever reads the clock or hass, forecasting/simulation and every test
built on determinism silently breaks. This lint test makes that structural
rule executable.

Since P2 the whole integration is held to part of this rule: outside the
clock seam (``runtime/clock.py``) nothing reads the wall clock.
"""

import ast
import re
from pathlib import Path

PACKAGE_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "adaptive_cover"
)
ENGINE_DIR = PACKAGE_DIR / "engine"
CLOCK_MODULE = PACKAGE_DIR / "runtime" / "clock.py"

FORBIDDEN = re.compile(
    r"homeassistant|datetime\.now|utcnow|date\.today|time\.time\(|import pandas"
    r"|import numpy|from numpy"
)

# datetime.now(), datetime.utcnow(), date.today(), dt_util.now(),
# dt_util.utcnow(), ... All of them read the wall clock.
CLOCK_ATTRIBUTES = {"now", "utcnow", "today"}
# time.time() and friends, when the module imports the time module.
TIME_MODULE_CALLS = {"time", "time_ns", "monotonic", "monotonic_ns", "perf_counter"}


def test_engine_dir_exists():
    assert ENGINE_DIR.is_dir()


def test_engine_has_no_forbidden_imports_or_clock_reads():
    offenders = []
    for path in sorted(ENGINE_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "Engine purity violated:\n" + "\n".join(offenders)


def _last_name(node: ast.expr) -> str:
    """The last identifier of an expression (``self.clock`` -> ``clock``)."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _last_name(node.func)
    if isinstance(node, ast.Subscript):
        return _last_name(node.value)
    return ""


def _imports_time_module(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Import) and any(a.name == "time" for a in node.names)
        for node in ast.walk(tree)
    )


def _clock_reads(path: Path) -> list[str]:
    """Every wall-clock read in one module that does not go through a clock."""
    tree = ast.parse(path.read_text(), filename=str(path))
    uses_time_module = _imports_time_module(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in CLOCK_ATTRIBUTES:
            # Allowed only on a clock: self.clock.now(tz), coordinator.clock...
            if "clock" not in _last_name(node.value).lower():
                found.append(f"{ast.unparse(node)} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and any(
            alias.name in CLOCK_ATTRIBUTES for alias in node.names
        ):
            found.append(f"from {node.module} import ... (line {node.lineno})")
        elif (
            uses_time_module
            and isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "time"
            and node.attr in TIME_MODULE_CALLS
        ):
            found.append(f"{ast.unparse(node)} (line {node.lineno})")
    return found


def test_only_the_clock_module_reads_the_wall_clock():
    """P2 clock seam: zero now()/utcnow()/today() outside runtime/clock.py."""
    assert CLOCK_MODULE.is_file()
    offenders = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if path == CLOCK_MODULE:
            continue
        rel = path.relative_to(PACKAGE_DIR)
        offenders += [f"{rel}: {read}" for read in _clock_reads(path)]
    assert not offenders, (
        "Wall-clock reads outside runtime/clock.py (use the coordinator's "
        "clock):\n" + "\n".join(offenders)
    )


def test_clock_scan_catches_every_form(tmp_path):
    """The scan itself: each forbidden form is reported, clock reads are not."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import time\n"
        "import datetime as dt\n"
        "from datetime import date, datetime\n"
        "from homeassistant.util import dt as dt_util\n"
        "from homeassistant.util.dt import utcnow\n"
        "a = dt.datetime.now(dt.UTC)\n"
        "b = datetime.now()\n"
        "c = date.today()\n"
        "d = dt_util.utcnow()\n"
        "e = dt_util.now()\n"
        "f = time.time()\n"
        "g = time.monotonic()\n"
        "ok1 = self.clock.utcnow()\n"
        "ok2 = coordinator.clock.now(tz)\n"
        "ok3 = targets[0][0].clock.utcnow()\n"
        "ok4 = moment.time()\n"
    )
    reads = _clock_reads(sample)
    assert len(reads) == 8, reads
    assert not any("clock" in read or "moment" in read for read in reads)

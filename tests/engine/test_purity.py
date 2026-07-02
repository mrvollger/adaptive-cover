"""The engine must stay pure: no HA imports, no wall-clock reads.

Time, sun position, and climate readings enter as explicit inputs; if the
engine ever reads the clock or hass, forecasting/simulation and every test
built on determinism silently breaks. This lint test makes that structural
rule executable.
"""

import re
from pathlib import Path

ENGINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "adaptive_cover"
    / "engine"
)

FORBIDDEN = re.compile(
    r"homeassistant|datetime\.now|utcnow|date\.today|time\.time\(|import pandas"
)


def test_engine_dir_exists():
    assert ENGINE_DIR.is_dir()


def test_engine_has_no_forbidden_imports_or_clock_reads():
    offenders = []
    for path in sorted(ENGINE_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "Engine purity violated:\n" + "\n".join(offenders)

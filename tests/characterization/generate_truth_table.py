"""Regenerate climate_truth_table.json from the CURRENT implementation.

Run from the repo root:

    PYTHONPATH=. python tests/characterization/generate_truth_table.py

Only regenerate when a behavior change is intended; the diff of the JSON is
the review artifact for that change.

The driver goes through ``engine.evaluate()`` with a fixed TimeContext
(truth_table_lib builds it), so no SunData replacement is needed; the
sanctioned seam for tests that DO need one is
``golden_lib.patch_sun_data``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    from tests.characterization.truth_table_lib import (
        TRUTH_TABLE_PATH,
        build_table,
    )

    table = build_table()
    TRUTH_TABLE_PATH.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {len(table)} rows to {TRUTH_TABLE_PATH}")


if __name__ == "__main__":
    main()

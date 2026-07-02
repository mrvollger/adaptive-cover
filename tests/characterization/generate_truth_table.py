"""Regenerate climate_truth_table.json from the CURRENT implementation.

Run from the repo root:

    PYTHONPATH=. python tests/characterization/generate_truth_table.py

Only regenerate when a behavior change is intended; the diff of the JSON is
the review artifact for that change.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _mock_sun_data():
    """Match tests/conftest.py mock_sun_data: sunset far ahead, sunrise far behind."""
    now_utc = datetime.now(UTC)
    tomorrow = now_utc + timedelta(days=1)
    yesterday = now_utc - timedelta(days=1)
    mock_instance = MagicMock()
    mock_instance.sunset.return_value = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 23, 59, 59, tzinfo=UTC
    )
    mock_instance.sunrise.return_value = datetime(
        yesterday.year, yesterday.month, yesterday.day, 0, 0, 1, tzinfo=UTC
    )
    times = pd.date_range(start=now_utc.date(), periods=289, freq="5min", tz="UTC")
    mock_instance.times = times
    mock_instance.solar_azimuth = [180.0] * len(times)
    mock_instance.solar_elevation = [45.0] * len(times)
    return mock_instance


def main() -> None:
    with patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=_mock_sun_data(),
    ):
        from tests.characterization.truth_table_lib import (
            TRUTH_TABLE_PATH,
            build_table,
        )

        table = build_table()
    TRUTH_TABLE_PATH.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
    print(f"Wrote {len(table)} rows to {TRUTH_TABLE_PATH}")


if __name__ == "__main__":
    main()

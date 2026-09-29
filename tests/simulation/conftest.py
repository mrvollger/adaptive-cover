"""Simulation fixtures.

Overrides the repo-wide autouse ``mock_sun_data`` fixture with a no-op:
the simulation harness installs its own real astral-backed fake for the
scenario's date and location (via ``golden_lib.patch_sun_data``).
"""

import pytest


@pytest.fixture(autouse=True)
def mock_sun_data():
    """No-op override; SimHouse controls the sun data override."""
    yield None

"""Simulation fixtures.

Overrides the repo-wide autouse ``mock_sun_data`` fixture with a no-op:
the simulation harness patches ``calculation.SunData`` itself with a real
astral-backed fake for the scenario's date and location.
"""

import pytest


@pytest.fixture(autouse=True)
def mock_sun_data():
    """No-op override; SimHouse controls the sun data patch."""
    yield None

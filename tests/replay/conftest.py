"""Replay fixtures.

Overrides the repo-wide autouse ``mock_sun_data`` fixture with a no-op:
the SimHouse harness patches the sun provider itself with real astral data
for the replay's date and location.
"""

import pytest


@pytest.fixture(autouse=True)
def mock_sun_data():
    """No-op override; SimHouse controls the sun data patch."""
    yield None

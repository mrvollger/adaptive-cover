"""The runtime tier runs without Home Assistant.

The root conftest's autouse fixtures build a ``hass`` instance (to enable
custom integrations) and patch the sun provider for every test. The runtime
components take no ``hass``, so this tier replaces both with no-ops: each
test calls a component directly, with fakes for what it reads.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """No hass in this tier: nothing to enable."""


@pytest.fixture(autouse=True)
def mock_sun_data():
    """No cover adapters in this tier: no sun to fake."""

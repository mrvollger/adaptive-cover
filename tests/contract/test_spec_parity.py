"""spec_parity.json matches what every settings surface shows today.

The snapshot pins each option key's kind, default, range, unit and
placement on the setup form, the options form, the change_settings and
add_entry services, services.yaml and the number entities. A change to any
of them must regenerate the snapshot in the same commit:

    PYTHONPATH=. pixi run python tests/contract/generate_spec_parity.py

and explain the diff in tests/contract/ledger.md.
"""

from __future__ import annotations

import difflib

import pytest

from custom_components.adaptive_cover.config_flow import HOUSE_SECTIONS

from .generate_spec_parity import SPEC_PARITY_PATH, build_snapshot, dumps


async def test_spec_parity_matches_the_code():
    fresh = dumps(await build_snapshot())
    committed = SPEC_PARITY_PATH.read_text(encoding="utf-8")
    if fresh != committed:
        diff = "".join(
            difflib.unified_diff(
                committed.splitlines(keepends=True),
                fresh.splitlines(keepends=True),
                "spec_parity.json (committed)",
                "spec_parity.json (code)",
                n=2,
            )
        )
        pytest.fail(
            "A settings surface changed. If intended, regenerate with "
            "`PYTHONPATH=. pixi run python tests/contract/generate_spec_parity.py` "
            "and add a ledger entry.\n" + diff[:6000]
        )


async def test_snapshot_covers_every_surface():
    """A walk that silently skips a surface would pin nothing."""
    forms = (await build_snapshot())["forms"]
    places = {name.split(" ")[0] for name in forms}
    setup_sections = (
        "window",
        "sun_limits",
        "advanced",
        "exceptions_positions",
        "exceptions_schedule",
        "exceptions_climate",
    )
    assert places >= {
        *(
            f"setup.{form}{section}"
            for form in ("first", "user", "reconfigure")
            for section in ("", *(f".{name}" for name in setup_sections))
        ),
        "options.house",
        *(f"options.house.{name}" for name in HOUSE_SECTIONS),
        "change_settings",
        "add_entry",
        "add_entry.baseline",
        "services_yaml.change_settings",
        "services_yaml.add_entry",
        "number",
    }

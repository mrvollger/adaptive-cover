"""What a window subentry stores since v2.1 (settings/window_record.py, P8).

- ``GEOMETRY_KEYS`` are the spec's window-home options minus the cover
  keys (the cover is stored once, as ``cover_entity_id``);
- a record round-trips through what the subentry stores;
- the runtime's flat view carries the cover as ``cover_entity_id`` and as
  the one-item ``group``;
- a v2.0 subentry (data and options verbatim, ADR 0006) reads as the same
  window: its one-time settings, its cover and its own overrides; the
  copies of the recurring settings, ``group`` and ``mode`` go;
- a v2.0 subentry without overrides of its own, or with several covers, is
  refused (the migration then leaves the house to v2.0.x).
"""

from __future__ import annotations

import pytest

from custom_components.adaptive_cover.const import (
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_DEFAULT_HEIGHT,
    CONF_DELTA_TIME,
    CONF_ENTITIES,
    CONF_EYE_HEIGHT,
    CONF_HEIGHT_WIN,
    CONF_MODE,
    CONF_SENSOR_TYPE,
    CONF_SUNSET_POS,
    SensorType,
)
from custom_components.adaptive_cover.settings.resolve import WindowOverrides
from custom_components.adaptive_cover.settings.spec import OPTS, Level, Scope
from custom_components.adaptive_cover.settings.window_record import (
    GEOMETRY_KEYS,
    RecordError,
    WindowRecord,
    is_v2_0,
    record_from_options,
    record_from_v2_0,
)

KEY = "01KWHKT5SWNSNC9QD4QC2SQMTR"
SUBENTRY = "01M3R05SHXAR0B3AX79H7NN1QJ"


def _v2_0(**options) -> dict:
    """A v2.0 window subentry's data: the window entry's data and options."""
    return {
        "window_key": KEY,
        "data": {"name": "Den south", CONF_SENSOR_TYPE: SensorType.BLIND},
        "options": {
            CONF_AZIMUTH: 190.0,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DEFAULT_HEIGHT: 97.0,  # a copy of a recurring setting
            CONF_DELTA_TIME: 2.0,  # another
            CONF_MODE: "basic",
            CONF_COVER_ENTITY: "cover.den_south_shades",
            CONF_ENTITIES: ["cover.den_south_shades"],
            "overrides": {
                "window_key": KEY,
                "values": {CONF_SUNSET_POS: 5},
                "legacy": {"lux_threshold": None},
            },
            **options,
        },
    }


def test_geometry_keys_are_the_window_home_options_but_the_cover():
    window_home = {opt.key for opt in OPTS if opt.home is Level.WINDOW}
    assert set(GEOMETRY_KEYS) == window_home - {CONF_COVER_ENTITY, CONF_ENTITIES}
    assert all(opt.scope is Scope.ONE_TIME for opt in OPTS if opt.key in GEOMETRY_KEYS)


def test_a_record_round_trips_through_what_the_subentry_stores():
    record = WindowRecord(
        name="Office north",
        cover="cover.office_north_shades",
        cover_type=SensorType.AWNING,
        geometry={CONF_AZIMUTH: 10, CONF_HEIGHT_WIN: 2.0},
        overrides=WindowOverrides(values={CONF_EYE_HEIGHT: 1.4}),
        window_key=KEY,
    )
    data = record.as_data()
    assert data == {
        "window_key": KEY,
        "name": "Office north",
        CONF_COVER_ENTITY: "cover.office_north_shades",
        "cover_type": SensorType.AWNING,
        "geometry": {CONF_AZIMUTH: 10, CONF_HEIGHT_WIN: 2.0},
        "overrides": {"values": {CONF_EYE_HEIGHT: 1.4}, "legacy": {}},
    }
    assert WindowRecord.from_data(data) == record
    # A window added as a subentry has no key of its own to store.
    new = WindowRecord(name="New", cover=None, cover_type=SensorType.BLIND)
    assert "window_key" not in new.as_data()
    assert WindowRecord.from_data(new.as_data()) == new


def test_the_flat_view_carries_the_cover_twice():
    record = record_from_options(
        "Office", SensorType.BLIND, {CONF_COVER_ENTITY: "cover.o", CONF_AZIMUTH: 90}
    )
    assert record.options == {
        CONF_AZIMUTH: 90,
        CONF_COVER_ENTITY: "cover.o",
        CONF_ENTITIES: ["cover.o"],
    }
    assert record.with_changes(cover=None).options[CONF_ENTITIES] == []
    assert record.with_changes(name="Den").cover == "cover.o"  # kept


def test_only_one_time_settings_are_geometry():
    with pytest.raises(RecordError, match=CONF_DEFAULT_HEIGHT):
        WindowRecord(
            name="x",
            cover=None,
            cover_type=SensorType.BLIND,
            geometry={CONF_DEFAULT_HEIGHT: 50},
        )


def test_a_v2_0_subentry_reads_as_the_same_window():
    data = _v2_0()
    assert is_v2_0(data)
    record = record_from_v2_0(data, SUBENTRY)
    assert record.window_key == KEY
    assert (record.name, record.cover_type) == ("Den south", SensorType.BLIND)
    assert record.cover == "cover.den_south_shades"
    assert record.geometry == {CONF_AZIMUTH: 190.0, CONF_HEIGHT_WIN: 2.1}
    assert record.overrides == WindowOverrides(
        values={CONF_SUNSET_POS: 5}, legacy={"lux_threshold": None}
    )
    stored = record.as_data()
    assert not is_v2_0(stored)
    # Only what the window uses: no copy of a recurring setting, no group.
    assert set(stored) == {
        "window_key",
        "name",
        CONF_COVER_ENTITY,
        "cover_type",
        "geometry",
        "overrides",
    }


def test_a_new_v2_0_window_is_keyed_by_its_subentry_id():
    data = _v2_0()
    del data["window_key"]
    data["options"]["overrides"]["window_key"] = SUBENTRY
    record = record_from_v2_0(data, SUBENTRY)
    assert record.window_key is None
    assert record.overrides.values == {CONF_SUNSET_POS: 5}


@pytest.mark.parametrize(
    "options",
    [
        {"overrides": {"window_key": "another window", "values": {}, "legacy": {}}},
        {"overrides": None},
        {CONF_ENTITIES: ["cover.a", "cover.b"]},
    ],
    ids=["a_copys_overrides", "no_overrides", "two_covers"],
)
def test_a_v2_0_window_that_cannot_be_read_is_refused(options):
    with pytest.raises(RecordError):
        record_from_v2_0(_v2_0(**options), SUBENTRY)

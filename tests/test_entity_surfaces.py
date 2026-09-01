"""Behavior tests for the per-entry entity surfaces (wp9-entity-surfaces).

Every assertion here goes through public seams only: a real config entry set
up via MockConfigEntry, mocked cover services, hass.states reads resolved
through the entity registry, and the documented diagnostics hook. No
coordinator internals, no private attributes.

Covers roadmap gaps: position-sensor, sun-time-sensors, next-change-sensor,
last-change-sensor, state-reason, sun-infront-binary,
conditional-entity-creation, contextual-logging, diagnostics-export.
Mutation targets: M40 (position sensor raw pre-transform), M41
(control-method winter/summer swap), M42 (sun-in-front inverted).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from unittest.mock import patch

from freezegun import freeze_time
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pandas as pd
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.adaptive_cover.const import (
    CONF_CLIMATE_MODE,
    CONF_DELTA_TIME,
    CONF_DISTANCE,
    CONF_ENTITIES,
    CONF_HEIGHT_WIN,
    CONF_INVERSE_STATE,
    CONF_IRRADIANCE_ENTITY,
    CONF_IRRADIANCE_THRESHOLD,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_MAX_ELEVATION,
    CONF_MIN_ELEVATION,
    CONF_OUTSIDETEMP_ENTITY,
    CONF_SENSOR_TYPE,
    CONF_TEMP_ENTITY,
    CONF_TEMP_HIGH,
    CONF_TEMP_LOW,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_STATE,
    DOMAIN,
    SensorType,
)
from custom_components.adaptive_cover.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.adaptive_cover.engine import geometry as engine_geometry

from .characterization.golden_lib import GOLDENS_DIR, SLC, FakeSunData
from .conftest import COMMON_OPTIONS

COVER = "cover.test_cover"

# Hand-computed vertical positions for h_win=2.1, distance=0.5, gamma=0:
# round((0.5 * tan(elev)) / 2.1 * 100)
POS_AT_45 = 24  # 0.5 * tan(45) = 0.500 -> 23.81
POS_AT_30 = 14  # 0.5 * tan(30) = 0.289 -> 13.75


def _entry(hass, name="Surface Test", covers=(COVER,), **extra):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": name, CONF_SENSOR_TYPE: SensorType.BLIND},
        options={
            **COMMON_OPTIONS,
            CONF_HEIGHT_WIN: 2.1,
            CONF_DISTANCE: 0.5,
            CONF_ENTITIES: list(covers),
            CONF_DELTA_TIME: 0,
            **extra,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _eid(hass, platform, entry, suffix):
    """Resolve an entity id from the entry's unique-id scheme."""
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{suffix}"
    )


def _set_cover(hass, position, state="open"):
    hass.states.async_set(
        COVER, state, {"current_position": position} if position is not None else {}
    )


def _set_sun(hass, elevation=45.0, azimuth=180.0):
    hass.states.async_set(
        "sun.sun",
        "above_horizon" if elevation > 0 else "below_horizon",
        {"azimuth": azimuth, "elevation": elevation},
    )


@pytest.fixture
def cover_calls(hass):
    return async_mock_service(hass, "cover", "set_cover_position")


def _fake_solar_day(date="2026-03-20"):
    """Patch SunData with a real astral day (overrides the autouse mock)."""
    sun = FakeSunData(SLC["lat"], SLC["lon"], SLC["tz"], pd.Timestamp(date))
    patcher = patch(
        "custom_components.adaptive_cover.calculation.SunData",
        return_value=sun,
    )
    return sun, patcher


class TestPositionSensor:
    """Gap position-sensor; kills M40."""

    async def test_position_sensor_state_and_updates(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _eid(hass, "sensor", entry, "Cover Position")
        assert eid is not None
        assert hass.states.get(eid).state == str(POS_AT_45)

        _set_sun(hass, elevation=30.0)
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == str(POS_AT_30)

    async def test_position_sensor_reports_transformed_value(
        self, hass, mock_sun_entity, cover_calls
    ):
        """With inverse on, the sensor shows the post-transform value and
        matches what is actually commanded (kills M40: raw pre-transform)."""
        _set_cover(hass, 60)
        entry = _entry(hass, **{CONF_INVERSE_STATE: True})
        await _setup(hass, entry)
        eid = _eid(hass, "sensor", entry, "Cover Position")
        assert hass.states.get(eid).state == str(100 - POS_AT_45)

        # Re-mock: the hub bootstrap during setup registers real cover
        # services on top of the pre-setup mock (same as test_service_calls).
        calls = async_mock_service(hass, "cover", "set_cover_position")
        _set_sun(hass, elevation=30.0)
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == str(100 - POS_AT_30)
        commanded = [c.data["position"] for c in calls]
        assert commanded == [100 - POS_AT_30]

    async def test_position_sensor_attributes(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        attrs = hass.states.get(_eid(hass, "sensor", entry, "Cover Position")).attributes
        assert attrs["intent"] == "calculated"
        assert isinstance(attrs["decision_trace"], list)
        assert isinstance(attrs["forecast_today"], list)
        assert attrs["sun"]["in_fov"] is True
        assert attrs["sun"]["azimuth"] == 180.0
        assert attrs["field_of_view"] == [90, 90]


class TestSunTimeSensors:
    """Gap sun-time-sensors: Start/End Sun honor the elevation band."""

    @staticmethod
    def _expected_span(sun, min_elev, max_elev, win_azi=180, fov=90):
        """First/last table row inside the FOV window with valid elevation."""
        azi_min = (win_azi - fov + 360) % 360
        azi_max = (win_azi + fov + 360) % 360
        valid = [
            i
            for i in range(len(sun.times))
            if (sun.solar_azimuth[i] - azi_min) % 360 <= (azi_max - azi_min) % 360
            and engine_geometry.valid_elevation(
                sun.solar_elevation[i], min_elev, max_elev
            )
        ]
        assert valid, "expected at least one in-window row"
        return (
            sun.times[valid[0]].to_pydatetime(),
            sun.times[valid[-1]].to_pydatetime(),
        )

    @freeze_time("2026-03-20 18:00:00")  # 12:00 in America/Denver
    async def test_sun_time_sensors_honor_band(
        self, hass, mock_sun_entity, cover_calls
    ):
        sun, patcher = _fake_solar_day()
        with patcher:
            plain = _entry(hass, name="No Band")
            banded = _entry(
                hass,
                name="Banded",
                **{CONF_MIN_ELEVATION: 15, CONF_MAX_ELEVATION: 45},
            )
            # Setting up the first entry loads every added entry of the domain.
            await _setup(hass, plain)

        def span_of(entry):
            start = hass.states.get(_eid(hass, "sensor", entry, "Start Sun")).state
            end = hass.states.get(_eid(hass, "sensor", entry, "End Sun")).state
            return dt_util.parse_datetime(start), dt_util.parse_datetime(end)

        plain_span = span_of(plain)
        banded_span = span_of(banded)
        assert plain_span == self._expected_span(sun, None, None)
        assert banded_span == self._expected_span(sun, 15, 45)
        # The band strictly narrows the engagement window.
        assert banded_span[0] > plain_span[0]
        assert banded_span[1] < plain_span[1]


# ---------------------------------------------------------------------------
# Next State Change sensor: entity-level absorption of goldens/next_events.txt
# ---------------------------------------------------------------------------

NEXT_EVENTS_GOLDEN = GOLDENS_DIR / "next_events.txt"
_NEXT_EVENT_RE = re.compile(
    r"^now=(?P<now>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) -> "
    r"name='(?P<name>[^']+)' time=(?P<time>\S+) pos=(?P<pos>\d+)$"
)


def _next_event_cases():
    cases = []
    for line in NEXT_EVENTS_GOLDEN.read_text().splitlines():
        match = _NEXT_EVENT_RE.match(line)
        if match:
            cases.append(
                (match["now"], match["name"], match["time"], int(match["pos"]))
            )
    assert len(cases) == 3, "goldens/next_events.txt changed shape"
    return cases


class TestNextChangeSensor:
    """Gap next-change-sensor, pinned against goldens/next_events.txt."""

    @pytest.mark.parametrize(
        ("now_str", "event_name", "time_str", "pos"),
        _next_event_cases(),
        ids=[c[0] for c in _next_event_cases()],
    )
    async def test_next_change_sensor_matches_golden(
        self, hass, cover_calls, now_str, event_name, time_str, pos
    ):
        await hass.config.async_set_time_zone(SLC["tz"])
        local_now = pd.Timestamp(now_str, tz=SLC["tz"]).to_pydatetime()
        _sun, patcher = _fake_solar_day()
        with freeze_time(local_now), patcher:
            _set_sun(hass)
            _set_cover(hass, 60)
            entry = _entry(hass, name=f"Next {now_str[-8:]}")
            await _setup(hass, entry)

            state = hass.states.get(_eid(hass, "sensor", entry, "Next State Change"))
            when = dt_util.parse_datetime(time_str)
            expected = (
                f"{event_name} at {dt_util.as_local(when).strftime('%H:%M')} "
                f"→ {pos}%"
            )
            assert state.state == expected
            assert state.attributes["event"] == event_name
            assert state.attributes["expected_position"] == pos
            assert dt_util.parse_datetime(state.attributes["expected_time"]) == when


class TestLastChangeSensor:
    """Gap last-change-sensor: 'old% -> new%: reason' for both change kinds."""

    async def test_last_change_sensor_format(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _eid(hass, "sensor", entry, "Last State Change")
        assert hass.states.get(eid).state == "No changes recorded"

        # Adaptive change: the computed position moves with the sun.
        _set_sun(hass, elevation=30.0)
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == (
            f"{POS_AT_45}% → {POS_AT_30}%: Sun in window (azi 180°, elev 30°)"
        )

        # Our own command lands...
        _set_cover(hass, POS_AT_30)
        await hass.async_block_till_done()
        # ...then a human moves the cover: manual override reason.
        _set_cover(hass, 90)
        await hass.async_block_till_done()
        state = hass.states.get(eid)
        assert state.state == f"{POS_AT_30}% → 90%: Manual override"
        assert state.attributes["old_position"] == POS_AT_30
        assert state.attributes["new_position"] == 90
        assert state.attributes["reason"] == "Manual override"
        assert state.attributes["changed_at"] is not None


class TestStateReason:
    """Gap state-reason, surfaced via the next-change sensor attributes."""

    async def test_reason_midday_sun_in_window(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        attrs = hass.states.get(
            _eid(hass, "sensor", entry, "Next State Change")
        ).attributes
        assert attrs["current_reason"] == "Sun in window (azi 180°, elev 45°)"

    async def test_reason_after_sunset(
        self, hass, mock_sun_data, cover_calls
    ):
        now = dt.datetime.now(dt.UTC)
        mock_sun_data.sunset.return_value = now - dt.timedelta(hours=2)
        mock_sun_data.sunrise.return_value = now - dt.timedelta(hours=14)
        _set_sun(hass, elevation=-9.0, azimuth=300.0)
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        attrs = hass.states.get(
            _eid(hass, "sensor", entry, "Next State Change")
        ).attributes
        assert attrs["current_reason"] == "Sunset position"
        # And the position sensor parks at the sunset position.
        assert hass.states.get(_eid(hass, "sensor", entry, "Cover Position")).state == "0"

    async def test_reason_during_manual_override(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        _set_sun(hass, elevation=30.0)
        await hass.async_block_till_done()
        _set_cover(hass, POS_AT_30)  # our command lands
        await hass.async_block_till_done()
        _set_cover(hass, 90)  # human move latches the override
        await hass.async_block_till_done()
        attrs = hass.states.get(
            _eid(hass, "sensor", entry, "Next State Change")
        ).attributes
        assert attrs["current_reason"] == "Manual override"


class TestControlMethodSensor:
    """Control-method sensor seasons at the entity boundary; kills M41."""

    async def test_control_method_sensor_seasons(
        self, hass, mock_sun_entity, cover_calls
    ):
        hass.states.async_set("sensor.indoor", "18.0")
        _set_cover(hass, 60)
        entry = _entry(
            hass,
            **{
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: "sensor.indoor",
                CONF_TEMP_LOW: 21,
                CONF_TEMP_HIGH: 25,
            },
        )
        await _setup(hass, entry)
        eid = _eid(hass, "sensor", entry, "Control Method")
        assert hass.states.get(eid).state == "winter"

        hass.states.async_set("sensor.indoor", "30.0")
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == "summer"


class TestSunInfrontBinary:
    """Gap sun-infront-binary; kills M42."""

    @pytest.mark.parametrize(
        ("elevation", "azimuth", "expected"),
        [
            (-10.0, 90.0, "off"),  # pre-dawn: below the horizon
            (45.0, 180.0, "on"),  # solar noon, square in the window
            (20.0, 300.0, "off"),  # sun left the 90/90 FOV
        ],
        ids=["pre_dawn", "solar_noon", "after_fov_exit"],
    )
    async def test_sun_infront_binary(
        self, hass, cover_calls, elevation, azimuth, expected
    ):
        _set_sun(hass, elevation=elevation, azimuth=azimuth)
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        eid = _eid(hass, "binary_sensor", entry, "Sun Infront")
        assert eid is not None
        assert hass.states.get(eid).state == expected


class TestConditionalEntityCreation:
    """Gap conditional-entity-creation: exactly the documented entity sets."""

    SWITCHES = (
        "Toggle Control",
        "Manual Override",
        "Climate Mode",
        "Outside Temperature",
        "Lux",
        "Irradiance",
    )

    def _present_switches(self, hass, entry):
        return {
            name for name in self.SWITCHES if _eid(hass, "switch", entry, name)
        }

    async def test_no_covers_no_switches_no_button(
        self, hass, mock_sun_entity, cover_calls
    ):
        entry = _entry(hass, covers=())
        await _setup(hass, entry)
        assert self._present_switches(hass, entry) == set()
        assert _eid(hass, "button", entry, "Reset Manual Override") is None
        # The sensor surface exists regardless.
        for sensor in (
            "Cover Position",
            "Start Sun",
            "End Sun",
            "Control Method",
            "Next State Change",
            "Last State Change",
        ):
            assert _eid(hass, "sensor", entry, sensor), sensor
        for binary in ("Sun Infront", "Manual Override"):
            assert _eid(hass, "binary_sensor", entry, binary), binary

    async def test_covers_basic_mode_switch_set(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        entry = _entry(hass)
        await _setup(hass, entry)
        assert self._present_switches(hass, entry) == {
            "Toggle Control",
            "Manual Override",
        }
        assert _eid(hass, "button", entry, "Reset Manual Override") is not None

    async def test_climate_with_all_aux_entities_full_switch_set(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        hass.states.async_set("sensor.indoor", "22.0")
        hass.states.async_set("sensor.outdoor", "20.0")
        hass.states.async_set("sensor.lux", "500")
        hass.states.async_set("sensor.irradiance", "200")
        hass.states.async_set("weather.home", "sunny")
        entry = _entry(
            hass,
            **{
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: "sensor.indoor",
                CONF_TEMP_LOW: 21,
                CONF_TEMP_HIGH: 25,
                CONF_WEATHER_ENTITY: "weather.home",
                CONF_WEATHER_STATE: ["sunny"],
                CONF_OUTSIDETEMP_ENTITY: "sensor.outdoor",
                CONF_LUX_ENTITY: "sensor.lux",
                CONF_LUX_THRESHOLD: 1000,
                CONF_IRRADIANCE_ENTITY: "sensor.irradiance",
                CONF_IRRADIANCE_THRESHOLD: 300,
            },
        )
        await _setup(hass, entry)
        assert self._present_switches(hass, entry) == set(self.SWITCHES)

    async def test_climate_without_aux_entities_climate_switch_only(
        self, hass, mock_sun_entity, cover_calls
    ):
        _set_cover(hass, 60)
        hass.states.async_set("sensor.indoor", "22.0")
        entry = _entry(
            hass,
            **{
                CONF_CLIMATE_MODE: True,
                CONF_TEMP_ENTITY: "sensor.indoor",
                CONF_TEMP_LOW: 21,
                CONF_TEMP_HIGH: 25,
            },
        )
        await _setup(hass, entry)
        assert self._present_switches(hass, entry) == {
            "Toggle Control",
            "Manual Override",
            "Climate Mode",
        }


class TestContextualLogging:
    """Gap contextual-logging: log lines carry the entry-name prefix."""

    async def test_log_prefix(self, hass, mock_sun_entity, cover_calls, caplog):
        caplog.set_level(logging.DEBUG, logger="custom_components.adaptive_cover")
        _set_cover(hass, 60)
        entry = _entry(hass, name="Prefix Probe")
        await _setup(hass, entry)
        _set_sun(hass, elevation=30.0)
        await hass.async_block_till_done()
        prefixed = [
            record
            for record in caplog.records
            if record.name.startswith("custom_components.adaptive_cover")
            and record.getMessage().startswith("[Prefix Probe]")
        ]
        assert prefixed, "no coordinator log line carried the config-name prefix"


class TestDiagnostics:
    """Gap diagnostics-export: payload shape of the documented hook."""

    async def test_diagnostics_shape(self, hass, mock_sun_entity, cover_calls):
        _set_cover(hass, 60)
        entry = _entry(hass, name="Diag Test")
        await _setup(hass, entry)
        payload = await async_get_config_entry_diagnostics(hass, entry)
        assert set(payload) == {
            "title",
            "type",
            "identifier",
            "config_data",
            "config_options",
        }
        assert payload["type"] == "config_entry"
        assert payload["identifier"] == entry.entry_id
        assert dict(payload["config_data"]) == dict(entry.data)
        assert dict(payload["config_options"]) == dict(entry.options)

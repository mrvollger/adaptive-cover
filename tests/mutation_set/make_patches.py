#!/usr/bin/env python3
"""Regenerate (or --check) the mutation patch files from the mutation table.

Run from the repo root after production code changes invalidate the diffs:

    python tests/mutation_set/make_patches.py          # rewrite patches
    python tests/mutation_set/make_patches.py --check  # CI gate, writes nothing

Each mutation is an exact-unique text replacement against the CURRENT
working-tree file; the script builds a unified diff (git-apply compatible),
verifies uniqueness, and writes ``M##_slug.patch`` plus ``manifest.json``.
Production source is never modified — diffs are computed in memory. A write
run builds every patch first and writes nothing if any mutation no longer
applies; it also deletes orphaned ``M##_*.patch`` files.

``--check`` exits 0 only if every mutation still applies (its target text
occurs exactly once) AND every committed patch file plus ``manifest.json`` is
byte-identical to what a write run would produce. Otherwise it lists each
stale / non-applying / missing / orphaned file and exits 1.

The mutation ids and semantics come from tests/refactor_roadmap.json's
``mutation_set``; a few mutations name the file the roadmap *conceptually*
assigned but land where the code actually lives (see ``deviation`` fields).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

COORD = "custom_components/adaptive_cover/coordinator.py"
GEOM = "custom_components/adaptive_cover/engine/geometry.py"
EVAL = "custom_components/adaptive_cover/engine/evaluate.py"
CALC = "custom_components/adaptive_cover/calculation.py"
SENSOR = "custom_components/adaptive_cover/sensor.py"
BINARY = "custom_components/adaptive_cover/binary_sensor.py"
INIT = "custom_components/adaptive_cover/__init__.py"
SURFACE = "custom_components/adaptive_cover/entity_surface.py"
SHARED = "custom_components/adaptive_cover/entity_shared.py"
SHADE_CONFIG = "custom_components/adaptive_cover/runtime/shade_config.py"
SCHEDULE = "custom_components/adaptive_cover/runtime/schedule.py"
GATES = "custom_components/adaptive_cover/runtime/gates.py"
COMMANDS = "custom_components/adaptive_cover/runtime/command_tracker.py"
DETECTOR = "custom_components/adaptive_cover/runtime/manual_detector.py"
OVERRIDES = "custom_components/adaptive_cover/runtime/override_tracker.py"
END_OF_DAY = "custom_components/adaptive_cover/runtime/end_of_day.py"
RESOLVE = "custom_components/adaptive_cover/settings/resolve.py"
LIFT = "custom_components/adaptive_cover/settings/lift.py"
DECIDER = "custom_components/adaptive_cover/runtime/decider.py"
HELPERS = "custom_components/adaptive_cover/helpers.py"
EXPLAINER = "custom_components/adaptive_cover/runtime/explainer.py"
WINDOW_COVER = "custom_components/adaptive_cover/window_cover.py"
SCHEMA = "custom_components/adaptive_cover/settings/schema.py"
CONFIG_FLOW = "custom_components/adaptive_cover/config_flow.py"
SETTINGS_SHADOW = "custom_components/adaptive_cover/settings/shadow.py"
SHADOW = "custom_components/adaptive_cover/shadow.py"
MODE = "custom_components/adaptive_cover/runtime/mode.py"
LAYERS = "custom_components/adaptive_cover/layers.py"
HOUSE_SETTINGS = "custom_components/adaptive_cover/house_settings.py"
CONSOLIDATE = "custom_components/adaptive_cover/consolidate.py"
HOUSE = "custom_components/adaptive_cover/house.py"


@dataclass
class Mutation:
    id: str
    slug: str
    file: str
    function: str
    description: str
    old: str
    new: str
    deviation: str | None = None


MUTATIONS: list[Mutation] = [
    # ---- group A: gates & timing windows -------------------------------
    Mutation(
        "M01",
        "delta_gate_ge",
        GATES,
        "GatePolicy.position_delta_ok",
        ">= min_change -> > (move exactly at threshold now blocked)",
        "            condition = abs(position - state) >= config.min_change",
        "            condition = abs(position - state) > config.min_change",
    ),
    Mutation(
        "M02",
        "quiet_hours_snap_bypass",
        GATES,
        "GatePolicy.quiet_hours_ok",
        "remove the snap-position early return (evening close swallowed in quiet window)",
        "        if not config.quiet_start or not config.quiet_end:\n"
        "            return True\n"
        "        if self.is_snap_position(state, config):\n"
        "            return True\n"
        "        now = now_local.time()",
        "        if not config.quiet_start or not config.quiet_end:\n"
        "            return True\n"
        "        now = now_local.time()",
    ),
    Mutation(
        "M03",
        "move_budget_ge",
        GATES,
        "GatePolicy.move_budget_ok",
        ">= max_moves_hour -> > (one extra move per rolling hour)",
        "        if len(history) >= config.max_moves_hour:",
        "        if len(history) > config.max_moves_hour:",
    ),
    Mutation(
        "M04",
        "time_delta_default_false",
        GATES,
        "GatePolicy.time_delta_ok",
        "no-previous-command branch return True -> return False",
        "            return condition\n"
        "        return True\n"
        "\n"
        "    def is_snap_position(",
        "            return condition\n"
        "        return False\n"
        "\n"
        "    def is_snap_position(",
    ),
    Mutation(
        "M05",
        "start_time_precedence_swap",
        SCHEDULE,
        "Schedule.after_start",
        "static CONF_START_TIME wins over the start-time entity (precedence swap)",
        "        if config.start_time_entity is not None:\n"
        "            time = self._read_time(config.start_time_entity, now.date())\n"
        "            if time is not None:\n"
        "                self.logger.debug(\n"
        '                    "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time\n'
        "                )\n"
        "                self.last_start = time\n"
        "                return now >= time\n"
        "            if config.start_time is None:\n"
        "                # Nothing to fall back to: wait until the entity reads a time.\n"
        "                self.logger.debug(\n"
        '                    "Start entity %s unreadable: not started", config.start_time_entity\n'
        "                )\n"
        "                return False\n"
        "        if config.start_time is not None:\n"
        "            time = get_datetime_from_str(config.start_time, default_date=now.date())\n"
        "\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time\n'
        "            )\n"
        "            self.last_start = time\n"
        "            return now >= time\n"
        "        return True",
        "        if config.start_time is not None:\n"
        "            time = get_datetime_from_str(config.start_time, default_date=now.date())\n"
        "\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time\n'
        "            )\n"
        "            self.last_start = time\n"
        "            return now >= time\n"
        "        if config.start_time_entity is not None:\n"
        "            time = self._read_time(config.start_time_entity, now.date())\n"
        "            if time is not None:\n"
        "                self.logger.debug(\n"
        '                    "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time\n'
        "                )\n"
        "                self.last_start = time\n"
        "                return now >= time\n"
        "            if config.start_time is None:\n"
        "                # Nothing to fall back to: wait until the entity reads a time.\n"
        "                self.logger.debug(\n"
        '                    "Start entity %s unreadable: not started", config.start_time_entity\n'
        "                )\n"
        "                return False\n"
        "        return True",
    ),
    Mutation(
        "M62",
        "fixed_start_not_recorded",
        SCHEDULE,
        "Schedule.after_start",
        "the fixed start time is not recorded, so start-after-end goes unreported",
        "            self.last_start = time\n"
        "            return now >= time\n"
        "        return True",
        "            return now >= time\n        return True",
    ),
    Mutation(
        "M63",
        "delta_gate_snap_list_drops_privacy",
        GATES,
        "GatePolicy.position_delta_ok",
        "the delta gate's snap list leaves out the privacy position",
        "            if self.is_snap_position(state, config):\n"
        "                condition = True\n"
        "            return condition",
        "            if state in [config.sunset_pos, config.default_height, 0, 100]:\n"
        "                condition = True\n"
        "            return condition",
    ),
    Mutation(
        "M64",
        "control_method_sticks",
        COORD,
        "climate_mode_data",
        "control_method keeps the last season when neither winter nor summer applies",
        '        else:\n            self.control_method = "intermediate"\n',
        "        else:\n            pass\n",
    ),
    Mutation(
        "M65",
        "adapters_ignore_coordinator_clock",
        CALC,
        "build_cover",
        "the cover adapters read the system clock instead of the coordinator's",
        "        hass, logger, geometry, sun=sun, timezone=timezone, clock=clock\n",
        "        hass, logger, geometry, sun=sun, timezone=timezone\n",
    ),
    Mutation(
        "M66",
        "last_move_time_in_process_zone",
        EXPLAINER,
        "Explainer.format_last_move",
        "the last-move HH:MM uses the process time zone instead of HA's",
        '        when = dt.datetime.fromisoformat(entry["time"]).astimezone(tz)',
        '        when = dt.datetime.fromisoformat(entry["time"]).astimezone()',
    ),
    Mutation(
        "M67",
        "time_entity_offset_ignored",
        HELPERS,
        "get_local_datetime_from_str",
        "a time entity's UTC offset is dropped: the instant is read as local wall time",
        "        parsed = parsed.astimezone(tz).replace(tzinfo=None)\n",
        "        parsed = parsed.replace(tzinfo=None)\n",
    ),
    Mutation(
        "M60",
        "unreadable_start_entity_counts_as_started",
        SCHEDULE,
        "Schedule.after_start",
        "an unreadable start entity with no fixed start counts as started",
        "                # Nothing to fall back to: wait until the entity reads a time.\n"
        "                self.logger.debug(\n"
        '                    "Start entity %s unreadable: not started", config.start_time_entity\n'
        "                )\n"
        "                return False\n",
        "                # Nothing to fall back to: wait until the entity reads a time.\n"
        "                self.logger.debug(\n"
        '                    "Start entity %s unreadable: not started", config.start_time_entity\n'
        "                )\n"
        "                return True\n",
    ),
    Mutation(
        "M06",
        "midnight_end_time_normalization",
        SCHEDULE,
        "Schedule.end_time",
        "drop the 00:00-means-next-midnight normalization",
        "        if time is not None and time.date() == today and time.time() == dt.time(0, 0):\n"
        "            time = time + dt.timedelta(days=1)\n"
        "        return time",
        "        return time",
    ),
    Mutation(
        "M61",
        "midnight_end_entity_not_normalized",
        SCHEDULE,
        "Schedule.end_time",
        "an end-time entity at 00:00 means the start of today (only the fixed end_time is normalized)",
        "        if time is not None and time.date() == today and time.time() == dt.time(0, 0):\n",
        "        if (\n"
        "            config.end_time_entity is None\n"
        "            and time is not None\n"
        "            and time.date() == today\n"
        "            and time.time() == dt.time(0, 0)\n"
        "        ):\n",
    ),
    Mutation(
        "M07",
        "gate_order_delta_before_manual",
        GATES,
        "GatePolicy.first_blocking_gate",
        "evaluate position-delta before the manual-override check "
        "(move_blocked_by names the wrong gate)",
        "        if cover.is_manual():\n"
        '            return "manual_override"\n'
        "        if cover.awaiting_target():",
        "        if not self.position_delta_ok(entity, cover.position(), state, config):\n"
        '            return "position_delta"\n'
        "        if cover.is_manual():\n"
        '            return "manual_override"\n'
        "        if cover.awaiting_target():",
    ),
    # ---- group B: manual override detection ----------------------------
    Mutation(
        "M08",
        "manual_detection_inverted",
        DETECTOR,
        "ManualDetector.check_landing",
        "new_position != our_state -> == (manual detection inverted)",
        "        if new_position != our_state:",
        "        if new_position == our_state:",
    ),
    Mutation(
        "M09",
        "own_landing_tolerance_flip",
        COMMANDS,
        "CommandTracker.is_own_landing",
        "<= TARGET_TOLERANCE -> > (own landings latch as manual)",
        "        return position is not None and abs(position - target) <= self.TARGET_TOLERANCE",
        "        return position is not None and abs(position - target) > self.TARGET_TOLERANCE",
    ),
    Mutation(
        "M10",
        "travel_direction_swap",
        COMMANDS,
        "CommandTracker.release_if_against",
        "expected opening/closing swapped in the travel-window direction check",
        '                expected = "opening" if target > old_pos else "closing"',
        '                expected = "closing" if target > old_pos else "opening"',
    ),
    Mutation(
        "M11",
        "manual_threshold_zero",
        DETECTOR,
        "ManualDetector.check_landing",
        "threshold check neutered: any nonzero diff latches",
        "                and abs(our_state - new_position) < manual_threshold",
        "                and abs(our_state - new_position) < 0",
    ),
    Mutation(
        "M12",
        "override_duration_minutes_to_hours",
        OVERRIDES,
        "OverrideTracker.set_duration",
        "override duration unit blown up 60x (minutes behave like hours)",
        "        self.reset_duration = dt.timedelta(**duration)\n",
        "        self.reset_duration = dt.timedelta(**duration) * 60\n",
    ),
    Mutation(
        "M13",
        "toggle_none_false_branch_swap",
        SHADE_CONFIG,
        "ControlState.clears_overrides",
        "swap the None (restart: preserve) and False (toggle-off: clear) branches",
        "        return self.manual is False",
        "        return self.manual is None",
    ),
    # ---- group C: end-of-day close lifecycle ---------------------------
    Mutation(
        "M14",
        "catchup_flag_inverted",
        END_OF_DAY,
        "EndOfDay.arm",
        "catch-up flag inversion <= -> > (on-time closes skip overridden covers)",
        "        self.is_catchup = end <= self._now_local()",
        "        self.is_catchup = end > self._now_local()",
    ),
    Mutation(
        "M15",
        "end_close_skips_transform",
        END_OF_DAY,
        "EndOfDay.close",
        "skip the sunset-position transform (raw value sent to interpolated/inverse covers)",
        "        target = int(transform(sunset_pos))",
        "        target = int(sunset_pos)",
    ),
    Mutation(
        "M16",
        "pending_snap_retry_inverted",
        END_OF_DAY,
        "EndOfDay.take_retry",
        "pending-snap retry control_toggle condition inverted",
        "        if pending is not None and control:",
        "        if pending is not None and not control:",
    ),
    Mutation(
        "M17",
        "end_time_rearm_skipped",
        END_OF_DAY,
        "EndOfDay.ensure_armed",
        "keep the stale timer: only arm once, never re-arm on an options change",
        "        if end and track_end_time and end != self.scheduled_time:",
        "        if end and track_end_time and self.scheduled_time is None:",
    ),
    Mutation(
        "M18",
        "late_fire_noop",
        END_OF_DAY,
        "EndOfDay._on_fire",
        "late delivery becomes a no-op (the historical 1-second-equality bug)",
        "        current_end = self._end_time()\n        self.logger.debug(",
        "        current_end = self._end_time()\n"
        "        if self.scheduled_time is not None and self._now_local() > (\n"
        "            self.scheduled_time + dt.timedelta(seconds=1)\n"
        "        ):\n"
        "            return\n"
        "        self.logger.debug(",
        deviation="roadmap wrote the guard as 'if now < end_time: return'; the "
        "kill-relevant behavior (a LATE fire is dropped) needs the inverse "
        "comparison, implemented here against the armed time.",
    ),
    # ---- group D: engine geometry --------------------------------------
    Mutation(
        "M19",
        "gamma_operand_swap",
        GEOM,
        "gamma",
        "operand swap in the relative sun angle",
        "    return (window_azimuth - solar_azimuth + 180) % 360 - 180",
        "    return (solar_azimuth - window_azimuth + 180) % 360 - 180",
    ),
    Mutation(
        "M20",
        "horizon_floor_dropped",
        GEOM,
        "valid_elevation",
        "drop the unconditional horizon floor",
        "    floor = 0 if min_elevation is None else min_elevation",
        "    floor = -90 if min_elevation is None else min_elevation",
    ),
    Mutation(
        "M21",
        "sunlit_top_sign_flip",
        GEOM,
        "sunlit_top",
        "overhang shadow-line sign flip",
        "    shadow_line = config.overhang.height_above_sill - config.overhang.depth * tan(",
        "    shadow_line = config.overhang.height_above_sill + config.overhang.depth * tan(",
    ),
    Mutation(
        "M22",
        "tilt_mode_divisor_swap",
        GEOM,
        "tilt_percentage",
        "mode1/mode2 divisor swap",
        '    if config.tilt_mode == "mode1":\n'
        "        return round(angle / 90 * 100)\n"
        "    return round(angle / 180 * 100)",
        '    if config.tilt_mode == "mode1":\n'
        "        return round(angle / 180 * 100)\n"
        "    return round(angle / 90 * 100)",
    ),
    Mutation(
        "M23",
        "fov_boundary_inclusive",
        GEOM,
        "sun_in_fov",
        "FOV boundary < -> <= (and mirror on -fov_right)",
        "    return bool(\n        (g < azi_min)\n        & (g > -azi_max)",
        "    return bool(\n        (g <= azi_min)\n        & (g >= -azi_max)",
    ),
    Mutation(
        "M24",
        "vertical_cos_multiply",
        GEOM,
        "vertical_blind_height",
        "distance / cos(gamma) -> distance * cos(gamma)",
        "        (config.distance_shaded_area / cos(rad(g))) * tan(rad(sun.elevation)),",
        "        (config.distance_shaded_area * cos(rad(g))) * tan(rad(sun.elevation)),",
    ),
    Mutation(
        "M25",
        "elevation_band_swapped",
        GEOM,
        "valid_elevation",
        "min and max band comparisons swapped",
        "    if elevation < floor:\n"
        "        return False\n"
        "    if max_elevation is not None and elevation > max_elevation:\n"
        "        return False",
        "    if elevation > floor:\n"
        "        return False\n"
        "    if max_elevation is not None and elevation < max_elevation:\n"
        "        return False",
    ),
    Mutation(
        "M26",
        "sunset_offset_sign_flip",
        GEOM,
        "sunset_valid",
        "sunset offset sign flip",
        "    after_sunset = ctx.now_utc > (\n"
        "        ctx.sunset_utc + timedelta(minutes=config.sunset_offset_min)\n"
        "    )",
        "    after_sunset = ctx.now_utc > (\n"
        "        ctx.sunset_utc - timedelta(minutes=config.sunset_offset_min)\n"
        "    )",
    ),
    Mutation(
        "M27",
        "sunrise_fallback_zero",
        SHADE_CONFIG,
        "_sunrise_offset",
        "sunrise-offset fallback falls back to 0 instead of sunset_offset",
        "    return options.get(CONF_SUNRISE_OFFSET, _read(options, CONF_SUNSET_OFFSET))",
        "    return options.get(CONF_SUNRISE_OFFSET, 0)",
        deviation="roadmap filed this under engine/geometry.py; the fallback "
        "actually lives in runtime/shade_config._sunrise_offset (moved there "
        "from coordinator.common_data in P3, ledger L0017).",
    ),
    Mutation(
        "M28",
        "privacy_offset_or_coercion",
        SHADE_CONFIG,
        "CoverGeometry.from_options",
        "'offset or DEFAULT' coercion so privacy_offset=0 becomes 30",
        "            privacy_offset=(\n"
        "                PRIVACY_OFFSET_FALLBACK if privacy_offset is None else privacy_offset\n"
        "            ),",
        "            privacy_offset=privacy_offset or PRIVACY_OFFSET_FALLBACK,",
        deviation="roadmap filed this under engine/geometry.py; the None-check "
        "actually lives in runtime/shade_config.CoverGeometry.from_options "
        "(moved there from coordinator._apply_extended_config in P3, ledger "
        "L0017).",
    ),
    # ---- group E: engine strategy --------------------------------------
    Mutation(
        "M29",
        "away_summer_opens",
        EVAL,
        "_evaluate_climate_normal",
        "away/summer branch return 0 -> return 100",
        "            if climate.is_summer:\n"
        '                trace.append("summer, away: close fully")\n'
        "                return 0, Intent.CLIMATE_BLOCK_HEAT",
        "            if climate.is_summer:\n"
        '                trace.append("summer, away: close fully")\n'
        "                return 100, Intent.CLIMATE_BLOCK_HEAT",
    ),
    Mutation(
        "M30",
        "privacy_not_first_in_climate",
        EVAL,
        "evaluate",
        "privacy-first ordering dropped for climate mode",
        "    if geometry.privacy_active(config, ctx) and privacy is not None:",
        "    if climate is None and geometry.privacy_active(config, ctx) and privacy is not None:",
    ),
    Mutation(
        "M31",
        "max_clamp_flip",
        EVAL,
        "_apply_limits",
        "max-clamp comparison flip",
        "    if max_position is not None and apply_max and result > max_position:",
        "    if max_position is not None and apply_max and result < max_position:",
    ),
    Mutation(
        "M32",
        "tilt_preset_swap",
        EVAL,
        "_evaluate_climate_tilt",
        "dim-summer 45 <-> presence 80 preset swap (trace strings untouched)",
        "            if climate.is_summer:\n"
        '                trace.append("tilt, summer, dim: 45 deg preset")\n'
        "                return 45 / degrees * 100, Intent.CLIMATE_TILT_PRESET\n"
        '            trace.append("tilt, dim: basic strategy")\n'
        "            return _evaluate_basic(config, sun, ctx, trace)\n"
        '        trace.append("tilt, presence: 80 deg preset")\n'
        "        return 80 / degrees * 100, Intent.CLIMATE_TILT_PRESET",
        "            if climate.is_summer:\n"
        '                trace.append("tilt, summer, dim: 45 deg preset")\n'
        "                return 80 / degrees * 100, Intent.CLIMATE_TILT_PRESET\n"
        '            trace.append("tilt, dim: basic strategy")\n'
        "            return _evaluate_basic(config, sun, ctx, trace)\n"
        '        trace.append("tilt, presence: 80 deg preset")\n'
        "        return 45 / degrees * 100, Intent.CLIMATE_TILT_PRESET",
    ),
    Mutation(
        "M33",
        "glare_band_nonempty_check",
        GEOM,
        "admit_no_glare_percentage",
        "ADMIT_NO_GLARE compares band non-empty instead of band-top vs eye height",
        "    top = sunlit_top(config, sun)\n"
        "    safe = glare_safe_height(config, sun)\n"
        "    if top <= safe:\n"
        "        return 100",
        "    top = sunlit_top(config, sun)\n"
        "    safe = glare_safe_height(config, sun)\n"
        "    if top <= 0:\n"
        "        return 100",
        deviation="roadmap filed this under engine/evaluate.py; the comparison "
        "actually lives in geometry.admit_no_glare_percentage.",
    ),
    Mutation(
        "M34",
        "season_boundary_low",
        CALC,
        "ClimateCoverData.is_summer",
        "summer test temp > temp_high -> temp > temp_low",
        "            is_it = self.get_current_temperature > self.temp_high and self.outside_high",
        "            is_it = self.get_current_temperature > self.temp_low and self.outside_high",
        deviation="roadmap filed this under engine/evaluate.py; the season "
        "threshold comparison actually lives in calculation.ClimateCoverData.",
    ),
    # ---- group F: output transforms & config ---------------------------
    Mutation(
        "M35",
        "inverse_state_identity",
        DECIDER,
        "inverse_state",
        "100 - state -> state",
        "def inverse_state(state: float) -> float:\n"
        '    """Inverse state."""\n'
        "    return 100 - state",
        "def inverse_state(state: float) -> float:\n"
        '    """Inverse state."""\n'
        "    return state",
    ),
    Mutation(
        "M36",
        "interp_xp_fp_swap",
        DECIDER,
        "Decider.interpolate",
        "np.interp xp/fp argument swap",
        "            state = interp(state, normal_range, new_range)",
        "            state = interp(state, new_range, normal_range)",
        deviation="P2 replaced np.interp with engine.numeric.interp (same "
        "semantics); the swap is anchored on the helper call.",
    ),
    Mutation(
        "M37",
        "interp_endpoint_snap_removed",
        DECIDER,
        "Decider.interpolate",
        "interpolation endpoint snap-to-0/100 removed",
        "            state = interp(state, normal_range, new_range)\n"
        "            if state == new_range[0]:\n"
        "                state = 0\n"
        "            if state == new_range[-1]:\n"
        "                state = 100\n"
        "        return state",
        "            state = interp(state, normal_range, new_range)\n"
        "        return state",
        deviation="P2 replaced np.interp with engine.numeric.interp (same "
        "semantics); re-anchored on the helper call.",
    ),
    Mutation(
        "M38",
        "inverse_applied_with_interp",
        DECIDER,
        "Decider.transform",
        "inverse-skipped-when-interp rule inverted (apply both transforms)",
        "        if self.inverse and not self.use_interpolation:",
        "        if self.inverse:",
    ),
    Mutation(
        "M39",
        "settings_merge_inverted",
        LAYERS,
        "window_options_after",
        "options merge inverted: existing options win over the requested changes",
        "            options[key] = value\n            continue\n",
        "            options.setdefault(key, value)\n            continue\n",
        deviation="roadmap filed this under coordinator.py 'config merge'; no "
        "literal data/options merge exists there. Since the P5 flip the "
        "merge of a window's edits (change_settings, the options form) into "
        "its options lives in layers.window_options_after.",
    ),
    # ---- group G: entity surfaces & routing ----------------------------
    Mutation(
        "M40",
        "position_sensor_raw_value",
        SENSOR,
        "AdaptiveCoverSensorEntity",
        "position sensor reports the raw pre-transform value",
        '        return self.data.states["state"]',
        "        return self.coordinator.default_state",
    ),
    Mutation(
        "M41",
        "control_method_swap",
        SENSOR,
        "AdaptiveCoverControlSensorEntity",
        "winter/summer branch swap at the sensor surface",
        '        return self.data.states["control"]',
        '        value = self.data.states["control"]\n'
        '        return {"winter": "summer", "summer": "winter"}.get(value, value)',
    ),
    Mutation(
        "M42",
        "sun_infront_inverted",
        BINARY,
        "AdaptiveCoverBinarySensor",
        "sun-in-front binary sensor inverted",
        "    @property\n"
        "    def is_on(self) -> bool:\n"
        '        """Return true if the binary sensor is on."""\n'
        "        return self.coordinator.data.states[self._key]",
        "    @property\n"
        "    def is_on(self) -> bool:\n"
        '        """Return true if the binary sensor is on."""\n'
        "        value = self.coordinator.data.states[self._key]\n"
        '        if self._key == "sun_motion":\n'
        "            return not value\n"
        "        return value",
    ),
    Mutation(
        "M43",
        "tilt_routed_to_position",
        COORD,
        "async_set_manual_position",
        "tilt entries routed to set_cover_position instead of set_cover_tilt_position",
        "                service = SERVICE_SET_COVER_TILT_POSITION",
        "                service = SERVICE_SET_COVER_POSITION",
    ),
    # ---- group J: layered settings (P5; M44, M49-M50 reserved by the plan) --
    Mutation(
        "M45",
        "area_floor_precedence_swapped",
        RESOLVE,
        "resolve_with_provenance",
        "area and floor precedence swapped: a floor value beats the area's",
        "        (Source.AREA, area.values),\n        (Source.FLOOR, floor.values),\n",
        "        (Source.FLOOR, floor.values),\n        (Source.AREA, area.values),\n",
    ),
    Mutation(
        "M46",
        "lift_drops_outlier",
        LIFT,
        "_OptionLift._windows",
        "the lift drops a window's outlier: it resolves to the inherited value",
        "            elif Level.WINDOW in self.allowed:\n"
        "                placed.overrides[win.key] = win.value\n",
        "            elif Level.WINDOW in self.allowed:\n                continue\n",
    ),
    # P5 flip, batch 1: Mode (auto / hold / off) and Hold.
    Mutation(
        "M47",
        "gates_ignore_mode_off",
        COORD,
        "async_handle_state_change",
        "gates ignore Mode off: the sun-tracking path moves a window whose Mode is off",
        '        """Handle state change from tracked entities (Mode off: no moves)."""\n'
        "        if self.control_toggle:\n",
        '        """Handle state change from tracked entities (Mode off: no moves)."""\n'
        "        if self.control_toggle is not None:\n",
    ),
    Mutation(
        "M48",
        "hold_ignores_its_duration",
        MODE,
        "ModeControl.hold",
        "hold ignores its duration: every hold lasts the override duration",
        "        length = duration if duration is not None else "
        "window.manager.reset_duration\n",
        "        length = window.manager.reset_duration\n",
    ),
    Mutation(
        "M51",
        "mode_restore_ignores_switch_fallback",
        MODE,
        "restored_mode",
        "Mode restore ignores the legacy switch fallback: a window whose "
        "Toggle Control was off comes back in auto on the first boot after the "
        "flip",
        '    if legacy_switch == "off":\n        return Restored(Mode.OFF)\n',
        "    if False:\n        return Restored(Mode.OFF)\n",
    ),
    # P5 flip, batch 2: the runtime acts on the layered settings.
    Mutation(
        "M90",
        "runtime_ignores_window_override",
        LAYERS,
        "effective_settings",
        "the runtime ignores a window's own values: every window acts on "
        "what it would inherit from its area, floor and the house",
        "                hub.options,\n                overrides,\n",
        "                hub.options,\n                WindowOverrides(),\n",
    ),
    Mutation(
        "M91",
        "set_profile_writes_the_wrong_level",
        LAYERS,
        "async_set_profile",
        "set_profile writes the wrong level: a floor's values are stored as "
        "the area of that id and an area's as the floor",
        "        bucket = FLOORS if level is Level.FLOOR else AREAS\n"
        "        profiles = dict(options.get(bucket) or {})\n",
        "        bucket = AREAS if level is Level.FLOOR else FLOORS\n"
        "        profiles = dict(options.get(bucket) or {})\n",
    ),
    Mutation(
        "M92",
        "house_setting_change_does_not_propagate",
        HOUSE_SETTINGS,
        "HouseSetting._store",
        "a house entity's change is stored but not propagated: the windows "
        "act on it only at their next refresh",
        "        await async_settings_changed(self.hass)\n",
        "        pass\n",
    ),
    # P5 shadow release (v1.18.0): the diff repair and the switch capture.
    Mutation(
        "M70",
        "shadow_diff_ignores_layered_key",
        SETTINGS_SHADOW,
        "differing_keys",
        "the shadow comparison ignores a differing key: only one-time options "
        "are compared, so a changed recurring option raises no repair issue",
        "        opt.key for opt in spec if not same_value(resolved[opt.key], "
        "legacy[opt.key])\n",
        "        opt.key\n"
        "        for opt in spec\n"
        "        if opt.home is Level.WINDOW\n"
        "        and not same_value(resolved[opt.key], legacy[opt.key])\n",
    ),
    Mutation(
        "M71",
        "switch_capture_ignores_restored_state",
        SHADOW,
        "_switch_state",
        "the lift ignores a switch's restored state and records its initial "
        "state instead (a switch the user turned on is lost at the flip)",
        "    return stored.state.state == STATE_ON\n",
        "    return switch.initial\n",
    ),
    # ---- group H: P1 entity surface ----------------------------------------
    Mutation(
        "M52",
        "card_sensor_disabled_by_default",
        SURFACE,
        "WINDOW_SURFACE",
        "Start sun sensor disabled by default while the card still reads it",
        '    ("sensor", "Start Sun"): SurfaceSpec("start_sun", _DIAG),',
        '    ("sensor", "Start Sun"): SurfaceSpec("start_sun", _DIAG, enabled_default=False),',
    ),
    Mutation(
        "M54",
        "area_copy_overwrites_user_area",
        SURFACE,
        "async_copy_cover_area",
        "window device takes the cover's area even when the user already set one",
        "    if device is None or device.area_id is not None:\n",
        "    if device is None:\n",
    ),
    Mutation(
        "M55",
        "override_until_without_duration",
        OVERRIDES,
        "OverrideTracker.expires_at",
        "override_until reports the latch time, not latch time + override duration",
        "        return latched_at + self.reset_duration\n",
        "        return latched_at\n",
        deviation="P5 flip: override_until (entity_shared.py) reads "
        "OverrideTracker.expires_at, which also knows a requested hold's end; "
        "the latch-time-plus-duration rule moved there.",
    ),
    # ---- group I: settings surfaces (P3) --------------------------------
    Mutation(
        "M56",
        "threshold_service_ignores_unit",
        INIT,
        "_async_register_services",
        "change_settings validates climate thresholds in °C whatever HA's unit",
        "        schema=change_settings_schema(temperature_unit),\n",
        "        schema=change_settings_schema(),\n",
    ),
    Mutation(
        "M57",
        "late_delivery_never_adopted",
        COMMANDS,
        "CommandTracker.adopt_late_delivery",
        "motion toward a failed-but-delivered command is never adopted as ours",
        "        sent = self._unconfirmed_sends.get(entity)\n",
        "        sent = None\n",
    ),
    Mutation(
        "M58",
        "missing_cover_commanded",
        COORD,
        "async_set_manual_position",
        "a window whose cover entity no longer exists still commands it",
        "        if current is None:\n            if entity not in self._missing_warned:\n",
        "        if False:\n            if entity not in self._missing_warned:\n",
    ),
    Mutation(
        "M59",
        "second_cover_accepted",
        WINDOW_COVER,
        "cover_problem",
        "a duplicate/second cover is accepted (the one-cover guard never objects)",
        "        problem = ERROR_COVER_IN_USE\n    return problem\n",
        "        problem = ERROR_COVER_IN_USE\n    return None\n",
    ),
    # ---- group K: the one-screen window form (P6; M80+) --------------------
    Mutation(
        "M80",
        "copy_from_copies_the_cover",
        SCHEMA,
        "copy_from_values",
        '"Copy from" also copies the source window\'s cover (its identity)',
        "        if opt.key in SETUP_OPTION_KEYS and opt.key not in IDENTITY_KEYS\n",
        "        if opt.key in SETUP_OPTION_KEYS\n",
    ),
    Mutation(
        "M81",
        "recurring_settings_outside_exceptions",
        SCHEMA,
        "setup_section",
        "recurring settings other than climate land in the one-time sections",
        "    if opt.scope is Scope.RECURRING:\n",
        "    if opt.scope is Scope.RECURRING and opt.group is Group.CLIMATE:\n",
    ),
    Mutation(
        "M82",
        "setup_form_drops_spec_defaults",
        SCHEMA,
        "_setup_marker",
        "the setup form gives no field its spec default (a new window stores None)",
        "    if default is not NO_DEFAULT:\n"
        '        kwargs["default"] = _default_factory(default)\n',
        '    if False:\n        kwargs["default"] = _default_factory(default)\n',
    ),
    Mutation(
        "M83",
        "cover_type_switch_not_shown",
        CONFIG_FLOW,
        "WindowForm.submit",
        "picking another cover type saves at once instead of showing its geometry",
        "        if filled or cover_type != self.cover_type:\n",
        "        if filled:\n",
    ),
    # P7 (v2.0): the house entry with window subentries; consolidation.
    Mutation(
        "M100",
        "consolidation_drops_subentry_link",
        CONSOLIDATE,
        "async_reparent_window",
        "consolidation moves an entity row to the house entry without its "
        "window subentry (HA then drops it when the device moves)",
        '            changes["config_subentry_id"] = subentry_id\n',
        '            changes["config_subentry_id"] = None\n',
    ),
    Mutation(
        "M101",
        "resolved_settings_change_after_consolidation",
        CONSOLIDATE,
        "_async_add_subentry",
        "the window subentry loses the window's stored overrides: after "
        "consolidation it re-adopts them from the legacy keys, so an edit made "
        "since the P5 flip is lost",
        "        data=_frozen(window_subentry_data(entry.entry_id, entry.data, "
        "entry.options)),\n",
        "        data=_frozen(\n"
        "            window_subentry_data(\n"
        '                entry.entry_id, entry.data, {**entry.options, "overrides": None}\n'
        "            )\n"
        "        ),\n",
    ),
    Mutation(
        "M102",
        "listener_rebuilds_every_window",
        HOUSE,
        "HouseRuntime.async_sync",
        "the house's update listener rebuilds every window, not only the "
        "changed one (plan M49)",
        "                if runtime.seen == self._seen(subentry_id):\n"
        "                    continue\n",
        "                if runtime.seen == self._seen(subentry_id):\n"
        "                    await self._async_stop_window(subentry_id)\n"
        "                    await self._async_start_window(subentry_id)\n"
        "                    continue\n",
    ),
    Mutation(
        "M103",
        "consolidation_leaves_the_device_unmoved",
        CONSOLIDATE,
        "async_reparent_window",
        "consolidation moves a window's entities but leaves its device on the "
        "window entry (plan M50)",
        "    if moved is None and legacy is not None:\n",
        "    if False:\n",
    ),
]


PATCH_NAME_RE = re.compile(r"^M\d+_.+\.patch$")
MANIFEST_NAME = "manifest.json"


class MutationError(Exception):
    """A mutation definition no longer applies to the current source."""


def patch_name(mutation: Mutation) -> str:
    """Return the patch file name for one mutation (``M##_slug.patch``)."""
    return f"{mutation.id}_{mutation.slug}.patch"


def build_patch(mutation: Mutation, repo_root: Path = REPO_ROOT) -> str:
    """Build a git-apply-compatible unified diff for one mutation.

    Raises
    ------
    MutationError
        If the target file is missing or the target text does not occur
        exactly once in it.
    """
    path = repo_root / mutation.file
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        raise MutationError(
            f"{mutation.id}: target file {mutation.file} does not exist"
        ) from err
    count = content.count(mutation.old)
    if count != 1:
        raise MutationError(
            f"{mutation.id}: expected exactly 1 occurrence of the target "
            f"text in {mutation.file} ({mutation.function}), found {count}. "
            "The production code changed; re-anchor the mutation in "
            "make_patches.py."
        )
    mutated = content.replace(mutation.old, mutation.new, 1)
    diff = difflib.unified_diff(
        content.splitlines(keepends=True),
        mutated.splitlines(keepends=True),
        fromfile=f"a/{mutation.file}",
        tofile=f"b/{mutation.file}",
    )
    header = f"diff --git a/{mutation.file} b/{mutation.file}\n"
    return header + "".join(diff)


def manifest_entry(mutation: Mutation) -> dict[str, str]:
    """Return the manifest.json record for one mutation."""
    entry = {
        "id": mutation.id,
        "file": mutation.file,
        "function": mutation.function,
        "description": mutation.description,
        "patch": patch_name(mutation),
    }
    if mutation.deviation:
        entry["deviation"] = mutation.deviation
    return entry


def generate(
    mutations: list[Mutation] = MUTATIONS, repo_root: Path = REPO_ROOT
) -> tuple[dict[str, str], list[str]]:
    """Build every output file in memory.

    Returns
    -------
    tuple
        ``(files, errors)``: ``files`` maps output file name -> exact text
        (patches plus ``manifest.json``); ``errors`` has one message per
        mutation that no longer applies or duplicates an id / patch name.
    """
    files: dict[str, str] = {}
    errors: list[str] = []
    seen_ids: set[str] = set()
    for mutation in mutations:
        name = patch_name(mutation)
        if mutation.id in seen_ids or name in files:
            errors.append(f"{mutation.id}: duplicate mutation id or patch name")
            continue
        seen_ids.add(mutation.id)
        try:
            files[name] = build_patch(mutation, repo_root)
        except MutationError as err:
            errors.append(str(err))
    manifest = [manifest_entry(m) for m in mutations]
    files[MANIFEST_NAME] = json.dumps(manifest, indent=1) + "\n"
    return files, errors


def _existing_patches(out_dir: Path) -> set[str]:
    return {p.name for p in out_dir.glob("*.patch") if PATCH_NAME_RE.match(p.name)}


def check(
    out_dir: Path = OUT_DIR,
    repo_root: Path = REPO_ROOT,
    mutations: list[Mutation] = MUTATIONS,
) -> list[str]:
    """Return every reason the committed mutation set is stale (empty = OK).

    Nothing is written.
    """
    files, problems = generate(mutations, repo_root)
    for name, text in files.items():
        path = out_dir / name
        if not path.exists():
            problems.append(f"{name}: missing (run make_patches.py)")
        elif path.read_bytes() != text.encode("utf-8"):
            problems.append(
                f"{name}: stale (differs from what make_patches.py generates)"
            )
    for orphan in sorted(_existing_patches(out_dir) - set(files)):
        problems.append(f"{orphan}: orphaned (no mutation definition)")
    return problems


def write(
    out_dir: Path = OUT_DIR,
    repo_root: Path = REPO_ROOT,
    mutations: list[Mutation] = MUTATIONS,
) -> list[str]:
    """Regenerate all patch files and manifest.json; return errors.

    All-or-nothing: if any mutation fails to apply, nothing is written and
    the errors are returned. Orphaned ``M##_*.patch`` files are deleted.
    """
    files, errors = generate(mutations, repo_root)
    if errors:
        return errors
    for name, text in files.items():
        (out_dir / name).write_bytes(text.encode("utf-8"))
    for orphan in sorted(_existing_patches(out_dir) - set(files)):
        (out_dir / orphan).unlink()
        print(f"Removed orphaned {orphan}")
    return []


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every mutation applies and the committed patches and "
        "manifest.json are byte-identical to a regeneration; write nothing",
    )
    args = parser.parse_args(argv)

    if args.check:
        problems = check()
        if problems:
            print(
                f"make_patches --check FAILED ({len(problems)} problem(s)):",
                file=sys.stderr,
            )
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print(
                "Fix: re-anchor non-applying mutations in make_patches.py, "
                "then run `python tests/mutation_set/make_patches.py`.",
                file=sys.stderr,
            )
            return 1
        print(
            f"make_patches --check OK: {len(MUTATIONS)} mutations apply; all "
            "patch files and manifest.json are up to date."
        )
        return 0

    errors = write()
    if errors:
        print("Nothing written; these mutations no longer apply:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(MUTATIONS)} patches + manifest.json to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

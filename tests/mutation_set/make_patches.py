#!/usr/bin/env python3
"""Regenerate the mutation patch files from the roadmap's mutation table.

Run from the repo root after production code changes invalidate the diffs:

    python tests/mutation_set/make_patches.py

Each mutation is an exact-unique text replacement against the CURRENT
working-tree file; the script builds a unified diff (git-apply compatible),
verifies uniqueness, and writes ``M##_slug.patch`` plus ``manifest.json``.
The working tree is never modified — diffs are computed in memory.

The mutation ids and semantics come from tests/refactor_roadmap.json's
``mutation_set``; a few mutations name the file the roadmap *conceptually*
assigned but land where the code actually lives (see ``deviation`` fields).
"""

from __future__ import annotations

import difflib
import json
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
        "M01", "delta_gate_ge", COORD, "check_position_delta",
        ">= min_change -> > (move exactly at threshold now blocked)",
        "            condition = abs(position - state) >= self.min_change",
        "            condition = abs(position - state) > self.min_change",
    ),
    Mutation(
        "M02", "quiet_hours_snap_bypass", COORD, "check_quiet_hours",
        "remove the snap-position early return (evening close swallowed in quiet window)",
        "        if not self.quiet_start or not self.quiet_end:\n"
        "            return True\n"
        "        if self._is_snap_position(state, options):\n"
        "            return True\n"
        "        now = self._now_local().time()",
        "        if not self.quiet_start or not self.quiet_end:\n"
        "            return True\n"
        "        now = self._now_local().time()",
    ),
    Mutation(
        "M03", "move_budget_ge", COORD, "check_move_budget",
        ">= max_moves_hour -> > (one extra move per rolling hour)",
        "        if len(history) >= self.max_moves_hour:",
        "        if len(history) > self.max_moves_hour:",
    ),
    Mutation(
        "M04", "time_delta_default_false", COORD, "check_time_delta",
        "no-previous-command branch return True -> return False",
        "            return condition\n"
        "        return True\n"
        "\n"
        "    @property\n"
        "    def pos_sun(self):",
        "            return condition\n"
        "        return False\n"
        "\n"
        "    @property\n"
        "    def pos_sun(self):",
    ),
    Mutation(
        "M05", "start_time_precedence_swap", COORD, "after_start_time",
        "static CONF_START_TIME wins over the start-time entity (precedence swap)",
        "        if self.start_time_entity is not None:\n"
        "            time = get_datetime_from_str(\n"
        "                get_safe_state(self.hass, self.start_time_entity),\n"
        "                default_date=now.date(),\n"
        "            )\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time\n'
        "            )\n"
        "            self._start_time = time\n"
        "            return now >= time\n"
        "        if self.start_time is not None:\n"
        "            time = get_datetime_from_str(\n"
        "                self.start_time, default_date=now.date()\n"
        "            )\n"
        "\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time\n'
        "            )\n"
        "            self._start_time\n"
        "            return now >= time\n"
        "        return True",
        "        if self.start_time is not None:\n"
        "            time = get_datetime_from_str(\n"
        "                self.start_time, default_date=now.date()\n"
        "            )\n"
        "\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s", time, now, now >= time\n'
        "            )\n"
        "            self._start_time\n"
        "            return now >= time\n"
        "        if self.start_time_entity is not None:\n"
        "            time = get_datetime_from_str(\n"
        "                get_safe_state(self.hass, self.start_time_entity),\n"
        "                default_date=now.date(),\n"
        "            )\n"
        "            self.logger.debug(\n"
        '                "Start time: %s, now: %s, now >= time: %s ", time, now, now >= time\n'
        "            )\n"
        "            self._start_time = time\n"
        "            return now >= time\n"
        "        return True",
    ),
    Mutation(
        "M06", "midnight_end_time_normalization", COORD, "_end_time",
        "drop the 00:00-means-next-midnight normalization",
        "            time = get_datetime_from_str(self.end_time, default_date=today)\n"
        "            if time.time() == dt.time(0, 0):\n"
        "                time = time + dt.timedelta(days=1)\n"
        "        return time",
        "            time = get_datetime_from_str(self.end_time, default_date=today)\n"
        "        return time",
    ),
    Mutation(
        "M07", "gate_order_delta_before_manual", COORD, "_first_blocking_gate",
        "evaluate position-delta before the manual-override check "
        "(move_blocked_by names the wrong gate)",
        "        if self.manager.is_cover_manual(entity):\n"
        '            return "manual_override"\n'
        "        if self.wait_for_target.get(entity):",
        "        if not self.check_position_delta(entity, state, options):\n"
        '            return "position_delta"\n'
        "        if self.manager.is_cover_manual(entity):\n"
        '            return "manual_override"\n'
        "        if self.wait_for_target.get(entity):",
    ),
    # ---- group B: manual override detection ----------------------------
    Mutation(
        "M08", "manual_detection_inverted", COORD,
        "AdaptiveCoverManager.handle_state_change",
        "new_position != our_state -> == (manual detection inverted)",
        "        if new_position != our_state:",
        "        if new_position == our_state:",
    ),
    Mutation(
        "M09", "own_landing_tolerance_flip", COORD, "_is_own_landing",
        "<= TARGET_TOLERANCE -> > (own landings latch as manual)",
        "        return (\n"
        "            position is not None\n"
        "            and abs(position - target) <= self.TARGET_TOLERANCE\n"
        "        )",
        "        return (\n"
        "            position is not None\n"
        "            and abs(position - target) > self.TARGET_TOLERANCE\n"
        "        )",
    ),
    Mutation(
        "M10", "travel_direction_swap", COORD, "async_check_cover_state_change",
        "expected opening/closing swapped in the travel-window direction check",
        '                expected = "opening" if target > old_pos else "closing"',
        '                expected = "closing" if target > old_pos else "opening"',
    ),
    Mutation(
        "M11", "manual_threshold_zero", COORD,
        "AdaptiveCoverManager.handle_state_change",
        "threshold check neutered: any nonzero diff latches",
        "                and abs(our_state - new_position) < manual_threshold",
        "                and abs(our_state - new_position) < 0",
    ),
    Mutation(
        "M12", "override_duration_minutes_to_hours", COORD,
        "_update_manager_and_covers",
        "override duration unit blown up 60x (minutes behave like hours)",
        "        self.manager.reset_duration = dt.timedelta(**self.manual_duration)",
        "        self.manager.reset_duration = dt.timedelta(**self.manual_duration) * 60",
    ),
    Mutation(
        "M13", "toggle_none_false_branch_swap", COORD, "_update_manager_and_covers",
        "swap the None (restart: preserve) and False (toggle-off: clear) branches",
        "        if self._manual_toggle is False:",
        "        if self._manual_toggle is None:",
    ),
    # ---- group C: end-of-day close lifecycle ---------------------------
    Mutation(
        "M14", "catchup_flag_inverted", COORD, "async_timed_end_time",
        "catch-up flag inversion <= -> > (on-time closes skip overridden covers)",
        "        self._end_time_is_catchup = self._end_time <= self._now_local()",
        "        self._end_time_is_catchup = self._end_time > self._now_local()",
    ),
    Mutation(
        "M15", "end_close_skips_transform", COORD, "async_handle_timed_refresh",
        "skip the sunset-position transform (raw value sent to interpolated/inverse covers)",
        "            target = int(self._transform_state(options.get(CONF_SUNSET_POS)))",
        "            target = int(options.get(CONF_SUNSET_POS))",
    ),
    Mutation(
        "M16", "pending_snap_retry_inverted", COORD, "async_check_cover_state_change",
        "pending-snap retry control_toggle condition inverted",
        "            if pending is not None and self.control_toggle:",
        "            if pending is not None and not self.control_toggle:",
    ),
    Mutation(
        "M17", "end_time_rearm_skipped", COORD, "_async_update_data",
        "keep the stale timer: only arm once, never re-arm on an options change",
        "        if (\n"
        "            self._end_time\n"
        "            and self._track_end_time\n"
        "            and self._end_time != self._scheduled_time\n"
        "        ):",
        "        if (\n"
        "            self._end_time\n"
        "            and self._track_end_time\n"
        "            and self._scheduled_time is None\n"
        "        ):",
    ),
    Mutation(
        "M18", "late_fire_noop", COORD, "async_timed_refresh",
        "late delivery becomes a no-op (the historical 1-second-equality bug)",
        "        current_end = self._end_time\n"
        "        self.logger.debug(",
        "        current_end = self._end_time\n"
        "        if self._scheduled_time is not None and self._now_local() > (\n"
        "            self._scheduled_time + dt.timedelta(seconds=1)\n"
        "        ):\n"
        "            return\n"
        "        self.logger.debug(",
        deviation="roadmap wrote the guard as 'if now < end_time: return'; the "
        "kill-relevant behavior (a LATE fire is dropped) needs the inverse "
        "comparison, implemented here against the armed time.",
    ),
    # ---- group D: engine geometry --------------------------------------
    Mutation(
        "M19", "gamma_operand_swap", GEOM, "gamma",
        "operand swap in the relative sun angle",
        "    return (window_azimuth - solar_azimuth + 180) % 360 - 180",
        "    return (solar_azimuth - window_azimuth + 180) % 360 - 180",
    ),
    Mutation(
        "M20", "horizon_floor_dropped", GEOM, "valid_elevation",
        "drop the unconditional horizon floor",
        "    floor = 0 if min_elevation is None else min_elevation",
        "    floor = -90 if min_elevation is None else min_elevation",
    ),
    Mutation(
        "M21", "sunlit_top_sign_flip", GEOM, "sunlit_top",
        "overhang shadow-line sign flip",
        "    shadow_line = config.overhang.height_above_sill - config.overhang.depth * tan(",
        "    shadow_line = config.overhang.height_above_sill + config.overhang.depth * tan(",
    ),
    Mutation(
        "M22", "tilt_mode_divisor_swap", GEOM, "tilt_percentage",
        "mode1/mode2 divisor swap",
        '    if config.tilt_mode == "mode1":\n'
        "        return round(angle / 90 * 100)\n"
        "    return round(angle / 180 * 100)",
        '    if config.tilt_mode == "mode1":\n'
        "        return round(angle / 180 * 100)\n"
        "    return round(angle / 90 * 100)",
    ),
    Mutation(
        "M23", "fov_boundary_inclusive", GEOM, "sun_in_fov",
        "FOV boundary < -> <= (and mirror on -fov_right)",
        "    return bool(\n"
        "        (g < azi_min)\n"
        "        & (g > -azi_max)",
        "    return bool(\n"
        "        (g <= azi_min)\n"
        "        & (g >= -azi_max)",
    ),
    Mutation(
        "M24", "vertical_cos_multiply", GEOM, "vertical_blind_height",
        "distance / cos(gamma) -> distance * cos(gamma)",
        "        (config.distance_shaded_area / cos(rad(g))) * tan(rad(sun.elevation)),",
        "        (config.distance_shaded_area * cos(rad(g))) * tan(rad(sun.elevation)),",
    ),
    Mutation(
        "M25", "elevation_band_swapped", GEOM, "valid_elevation",
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
        "M26", "sunset_offset_sign_flip", GEOM, "sunset_valid",
        "sunset offset sign flip",
        "    after_sunset = ctx.now_utc > (\n"
        "        ctx.sunset_utc + timedelta(minutes=config.sunset_offset_min)\n"
        "    )",
        "    after_sunset = ctx.now_utc > (\n"
        "        ctx.sunset_utc - timedelta(minutes=config.sunset_offset_min)\n"
        "    )",
    ),
    Mutation(
        "M27", "sunrise_fallback_zero", COORD, "common_data",
        "sunrise-offset fallback falls back to 0 instead of sunset_offset",
        "            options.get(CONF_SUNRISE_OFFSET, options.get(CONF_SUNSET_OFFSET)),",
        "            options.get(CONF_SUNRISE_OFFSET, 0),",
        deviation="roadmap filed this under engine/geometry.py; the fallback "
        "actually lives in coordinator.common_data.",
    ),
    Mutation(
        "M28", "privacy_offset_or_coercion", COORD, "_apply_extended_config",
        "'offset or DEFAULT' coercion so privacy_offset=0 becomes 30",
        "                offset_min=30 if _privacy_offset is None else _privacy_offset,",
        "                offset_min=_privacy_offset or 30,",
        deviation="roadmap filed this under engine/geometry.py; the None-check "
        "actually lives in coordinator._apply_extended_config.",
    ),
    # ---- group E: engine strategy --------------------------------------
    Mutation(
        "M29", "away_summer_opens", EVAL, "_evaluate_climate_normal",
        "away/summer branch return 0 -> return 100",
        "            if climate.is_summer:\n"
        '                trace.append("summer, away: close fully")\n'
        "                return 0, Intent.CLIMATE_BLOCK_HEAT",
        "            if climate.is_summer:\n"
        '                trace.append("summer, away: close fully")\n'
        "                return 100, Intent.CLIMATE_BLOCK_HEAT",
    ),
    Mutation(
        "M30", "privacy_not_first_in_climate", EVAL, "evaluate",
        "privacy-first ordering dropped for climate mode",
        "    if geometry.privacy_active(config, ctx):",
        "    if climate is None and geometry.privacy_active(config, ctx):",
    ),
    Mutation(
        "M31", "max_clamp_flip", EVAL, "_apply_limits",
        "max-clamp comparison flip",
        "    if apply_max and result > limits.max_position:",
        "    if apply_max and result < limits.max_position:",
    ),
    Mutation(
        "M32", "tilt_preset_swap", EVAL, "_evaluate_climate_tilt",
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
        "M33", "glare_band_nonempty_check", GEOM, "admit_no_glare_percentage",
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
        "M34", "season_boundary_low", CALC, "ClimateCoverData.is_summer",
        "summer test temp > temp_high -> temp > temp_low",
        "            is_it = self.get_current_temperature > self.temp_high and self.outside_high",
        "            is_it = self.get_current_temperature > self.temp_low and self.outside_high",
        deviation="roadmap filed this under engine/evaluate.py; the season "
        "threshold comparison actually lives in calculation.ClimateCoverData.",
    ),
    # ---- group F: output transforms & config ---------------------------
    Mutation(
        "M35", "inverse_state_identity", COORD, "inverse_state",
        "100 - state -> state",
        "def inverse_state(state: int) -> int:\n"
        '    """Inverse state."""\n'
        "    return 100 - state",
        "def inverse_state(state: int) -> int:\n"
        '    """Inverse state."""\n'
        "    return state",
    ),
    Mutation(
        "M36", "interp_xp_fp_swap", COORD, "interpolate_states",
        "np.interp xp/fp argument swap",
        "            state = np.interp(state, normal_range, new_range)",
        "            state = np.interp(state, new_range, normal_range)",
    ),
    Mutation(
        "M37", "interp_endpoint_snap_removed", COORD, "interpolate_states",
        "interpolation endpoint snap-to-0/100 removed",
        "            state = np.interp(state, normal_range, new_range)\n"
        "            if state == new_range[0]:\n"
        "                state = 0\n"
        "            if state == new_range[-1]:\n"
        "                state = 100\n"
        "        return state",
        "            state = np.interp(state, normal_range, new_range)\n"
        "        return state",
    ),
    Mutation(
        "M38", "inverse_applied_with_interp", COORD, "_transform_state",
        "inverse-skipped-when-interp rule inverted (apply both transforms)",
        "        if self._inverse_state and not self._use_interpolation:",
        "        if self._inverse_state:",
    ),
    Mutation(
        "M39", "settings_merge_inverted", INIT, "handle_change_settings",
        "options merge inverted: existing options win over the requested changes",
        '            update_kwargs["options"] = {**entry.options, **changes}',
        '            update_kwargs["options"] = {**changes, **entry.options}',
        deviation="roadmap filed this under coordinator.py 'config merge'; no "
        "literal data/options merge exists there — the real options-over-"
        "changes merge lives in __init__.handle_change_settings.",
    ),
    # ---- group G: entity surfaces & routing ----------------------------
    Mutation(
        "M40", "position_sensor_raw_value", SENSOR, "AdaptiveCoverSensorEntity",
        "position sensor reports the raw pre-transform value",
        '        return self.data.states["state"]',
        "        return self.coordinator.default_state",
    ),
    Mutation(
        "M41", "control_method_swap", SENSOR, "AdaptiveCoverControlSensorEntity",
        "winter/summer branch swap at the sensor surface",
        '        return self.data.states["control"]',
        '        value = self.data.states["control"]\n'
        '        return {"winter": "summer", "summer": "winter"}.get(value, value)',
    ),
    Mutation(
        "M42", "sun_infront_inverted", BINARY, "AdaptiveCoverBinarySensor",
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
        "M43", "tilt_routed_to_position", COORD, "async_set_manual_position",
        "tilt entries routed to set_cover_position instead of set_cover_tilt_position",
        "                service = SERVICE_SET_COVER_TILT_POSITION",
        "                service = SERVICE_SET_COVER_POSITION",
    ),
]


def build_patch(mutation: Mutation) -> str:
    """Build a git-apply-compatible unified diff for one mutation."""
    path = REPO_ROOT / mutation.file
    content = path.read_text()
    count = content.count(mutation.old)
    if count != 1:
        raise SystemExit(
            f"{mutation.id}: expected exactly 1 occurrence of the target "
            f"text in {mutation.file}, found {count}. The production code "
            "changed; update make_patches.py."
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


def main() -> None:
    manifest = []
    for mutation in MUTATIONS:
        patch_name = f"{mutation.id}_{mutation.slug}.patch"
        (OUT_DIR / patch_name).write_text(build_patch(mutation))
        entry = {
            "id": mutation.id,
            "file": mutation.file,
            "function": mutation.function,
            "description": mutation.description,
            "patch": patch_name,
        }
        if mutation.deviation:
            entry["deviation"] = mutation.deviation
        manifest.append(entry)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n"
    )
    print(f"Wrote {len(manifest)} patches + manifest.json to {OUT_DIR}")


if __name__ == "__main__":
    main()

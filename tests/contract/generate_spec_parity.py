"""Snapshot every settings surface into ``spec_parity.json``.

Run from the repo root:

    PYTHONPATH=. pixi run python tests/contract/generate_spec_parity.py

The snapshot records, for every option key, how each surface that shows or
accepts it describes it today: kind, default, min, max, step, unit and the
places (surface, form, cover type, climate mode, HA temperature unit) where
it appears. The surfaces are:

- ``setup.user.<section>`` / ``setup.reconfigure.<section>``: the
  one-screen window form (ConfigFlow add and Reconfigure steps), for each
  cover type (it replaced the page-by-page wizard in P6);
- ``options.init.<section>``: the one-page options form, for each cover type
  with climate mode off and on;
- ``change_settings`` / ``add_entry``: the service schemas as registered;
  ``add_entry`` also records the baseline options an entry gets without
  ``copy_from`` (its effective defaults);
- ``services_yaml.<service>``: the service field selectors in services.yaml
  (what the HA service UI shows);
- ``number``: the live number entities.

The ``forms`` block records the field order of every form and section (the
order the UI shows). For the service schemas and the number entities it
records the sorted key set instead: their order is not user-visible.

Every surface is read through the code that serves it (the flow handlers,
the service registration, the number platform setup), driven with small
fakes, so the snapshot follows the code wherever the schemas come from.
Each place is walked under both HA temperature units (°C and °F).

Only regenerate when a surface change is intended. The diff of the JSON is
the review artifact for that change, and needs a ledger entry
(tests/contract/ledger.md).
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import voluptuous as vol
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from homeassistant.data_entry_flow import section  # noqa: E402
from homeassistant.helpers import selector  # noqa: E402
from homeassistant.util.unit_system import (  # noqa: E402
    METRIC_SYSTEM,
    US_CUSTOMARY_SYSTEM,
)

SPEC_PARITY_PATH = Path(__file__).resolve().parent / "spec_parity.json"
PACKAGE_DIR = REPO_ROOT / "custom_components" / "adaptive_cover"

COVER_TYPES = ("cover_awning", "cover_blind", "cover_tilt")
CLIMATES = ("off", "on")
UNIT_SYSTEMS = {"°C": METRIC_SYSTEM, "°F": US_CUSTOMARY_SYSTEM}
UNITS = tuple(UNIT_SYSTEMS)

# One observation context: (cover type, climate mode, HA temperature unit).
Context = tuple[str, str, str]
ALL_CONTEXTS: tuple[Context, ...] = tuple(
    (t, c, u) for t in COVER_TYPES for c in CLIMATES for u in UNITS
)


# --------------------------------------------------------------- describe


def _num(value: Any) -> Any:
    """Normalize numbers so 10 and 10.0 snapshot the same."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_num(v) for v in value]
    if isinstance(value, dict):
        return {k: _num(v) for k, v in value.items()}
    return value


def _clean(config: dict[str, Any]) -> dict[str, Any]:
    return {k: _num(v) for k, v in sorted(config.items()) if v is not None}


def _describe_selector(validator: selector.Selector) -> dict[str, Any]:
    ((kind, config),) = validator.serialize()["selector"].items()
    if kind == "boolean":
        return {"kind": "boolean"}
    config = dict(config)
    if "unit_of_measurement" in config:
        config["unit"] = config.pop("unit_of_measurement")
    return {"kind": kind, **_clean(config)}


def _describe_bounds(validator: vol.Range | vol.Length) -> dict[str, Any]:
    names = (
        ("min", "max")
        if isinstance(validator, vol.Range)
        else ("min_length", "max_length")
    )
    out = {
        name: _num(value)
        for name, value in zip(names, (validator.min, validator.max), strict=True)
        if value is not None
    }
    if isinstance(validator, vol.Range):
        if not validator.min_included:
            out["min_excluded"] = True
        if not validator.max_included:
            out["max_excluded"] = True
    return out


def _describe_all(validator: vol.All) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part in validator.validators:
        described = describe(part)
        if "list" in (out.get("kind"), described.get("kind")):
            # vol.All(vol.Coerce(list), [str]): the list shape wins.
            out.pop("kind", None)
            described = {**described, "kind": "list"}
        out.update(described)
    return out


def _describe_any(validator: vol.Any) -> dict[str, Any]:
    options = [v for v in validator.validators if v is not None]
    if len(options) == 1:
        out = describe(options[0])
    else:
        out = {"kind": "any", "any_of": [describe(v) for v in options]}
    if len(options) != len(validator.validators):
        out["nullable"] = True
    return out


_TYPE_KINDS = {str: "string", int: "int", float: "float", dict: "dict", list: "list"}


def describe(validator: Any) -> dict[str, Any]:
    """Describe a voluptuous validator or HA selector as plain data.

    Raises TypeError for anything unknown, so a new validator shape makes
    the generator fail loudly instead of recording something vague.
    """
    if isinstance(validator, selector.Selector):
        return _describe_selector(validator)
    if validator is None:
        return {"kind": "null"}
    if validator is bool:
        return {"kind": "boolean"}
    if isinstance(validator, type) and validator in _TYPE_KINDS:
        return {"kind": _TYPE_KINDS[validator]}
    if isinstance(validator, list):
        (item,) = validator
        return {"kind": "list", "items": describe(item)["kind"]}
    if isinstance(validator, vol.Coerce):
        return {"kind": _TYPE_KINDS[validator.type]}
    if isinstance(validator, (vol.Range, vol.Length)):
        return _describe_bounds(validator)
    if isinstance(validator, vol.In):
        return {"kind": "enum", "options": list(validator.container)}
    if isinstance(validator, vol.Match):
        return {"kind": "string", "pattern": validator.pattern.pattern}
    if isinstance(validator, vol.All):
        return _describe_all(validator)
    if isinstance(validator, vol.Any):
        return _describe_any(validator)
    if callable(validator) and getattr(validator, "__name__", "") == "Boolean":
        return {"kind": "boolean"}
    raise TypeError(f"describe() does not know {validator!r}")


def describe_marker(marker: Any, validator: Any) -> dict[str, Any]:
    """Describe one form field: its validator plus required/default/suggested."""
    out = describe(validator)
    out["required"] = isinstance(marker, vol.Required)
    default = marker.default
    if default is not vol.UNDEFINED:
        value = default() if callable(default) else default
        if value is not vol.UNDEFINED:
            out["default"] = _num(value)
    description = getattr(marker, "description", None)
    if isinstance(description, dict) and "suggested_value" in description:
        out["suggested"] = True
    return out


# ------------------------------------------------------------ observation


class Observations:
    """(place, key) -> {context: descriptor}, plus place -> {context: order}."""

    def __init__(self) -> None:
        self.fields: dict[tuple[str, str], dict[Context, dict[str, Any]]] = defaultdict(
            dict
        )
        self.forms: dict[str, dict[Context, tuple[str, ...]]] = defaultdict(dict)

    def add_form(
        self,
        place: str,
        schema: vol.Schema,
        contexts: Iterable[Context],
    ) -> None:
        """Record a form (or section) schema at ``place`` for ``contexts``."""
        contexts = list(contexts)
        order: list[str] = []
        for marker, validator in schema.schema.items():
            key = str(marker.schema)
            order.append(key)
            if isinstance(validator, section):
                self.add_form(f"{place}.{key}", validator.schema, contexts)
                continue
            described = describe_marker(marker, validator)
            for ctx in contexts:
                self.fields[(place, key)][ctx] = described
        for ctx in contexts:
            self.forms[place][ctx] = tuple(order)

    def add_field(
        self, place: str, key: str, described: dict[str, Any], contexts
    ) -> None:
        for ctx in contexts:
            self.fields[(place, key)][ctx] = described


def _contexts(
    types: Iterable[str] = COVER_TYPES,
    climates: Iterable[str] = CLIMATES,
    units: Iterable[str] = UNITS,
) -> list[Context]:
    return [(t, c, u) for t in types for c in climates for u in units]


def _fake_hass(unit: str, **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(units=UNIT_SYSTEMS[unit]), data={}, **extra
    )


def _prepare_flow(flow: Any, hass: Any, handler: str) -> Any:
    flow.hass = hass
    flow.handler = handler
    flow.flow_id = f"spec-parity-{handler}"
    flow.context = {"source": "user"}
    return flow


def _form(result: dict[str, Any], step_id: str) -> vol.Schema:
    assert result["type"] == "form", result
    assert result["step_id"] == step_id, (result["step_id"], step_id)
    return result["data_schema"]


def _fake_window(entry_id: str, cover_type: str) -> SimpleNamespace:
    """A window config entry, as the setup form reads one."""
    return SimpleNamespace(
        entry_id=entry_id,
        title=f"Spec parity {entry_id}",
        domain="adaptive_cover",
        data={"name": f"Spec parity {entry_id}", "sensor_type": cover_type},
        options={},
    )


def _entries(*windows: SimpleNamespace) -> SimpleNamespace:
    """The config-entry registry calls the setup form makes."""
    by_id = {window.entry_id: window for window in windows}
    return SimpleNamespace(
        async_entries=lambda *_a, **_kw: list(windows),
        async_get_entry=by_id.get,
        async_get_known_entry=by_id.__getitem__,
    )


async def _walk_setup(obs: Observations) -> None:
    """The one-screen window form, per cover type and unit.

    ``setup.user``: the add form (one window exists, so "Copy from" shows),
    shown for each cover type the way a user gets there: the blind form
    first, then the type picked. ``setup.reconfigure``: the Reconfigure
    form of a window of each type. Neither depends on climate mode.
    """
    from custom_components.adaptive_cover.config_flow import ConfigFlowHandler

    source = _fake_window("window", "cover_blind")
    for unit in UNITS:
        for cover_type in COVER_TYPES:
            ctx = _contexts(types=[cover_type], units=[unit])
            hass = _fake_hass(unit, config_entries=_entries(source))
            flow = _prepare_flow(ConfigFlowHandler(), hass, "setup")
            result = await flow.async_step_user()
            if cover_type != "cover_blind":
                result = await flow.async_step_user(
                    {
                        "window": {
                            "cover_entity_id": "cover.spec_parity",
                            "sensor_type": cover_type,
                        }
                    }
                )
            obs.add_form("setup.user", _form(result, "user"), ctx)

            target = _fake_window("reconfigured", cover_type)
            hass = _fake_hass(unit, config_entries=_entries(source, target))
            flow = _prepare_flow(ConfigFlowHandler(), hass, "setup")
            flow.context = {"source": "reconfigure", "entry_id": target.entry_id}
            result = await flow.async_step_reconfigure()
            obs.add_form("setup.reconfigure", _form(result, "reconfigure"), ctx)


async def _walk_options(obs: Observations) -> None:
    """The options form, per cover type, climate mode and unit."""
    from custom_components.adaptive_cover.config_flow import ConfigFlowHandler

    for unit in UNITS:
        for cover_type in COVER_TYPES:
            for climate in CLIMATES:
                entry = SimpleNamespace(
                    entry_id="spec-parity",
                    data={"name": "Spec parity", "sensor_type": cover_type},
                    options={"climate_mode": climate == "on"},
                )
                flow = _prepare_flow(
                    ConfigFlowHandler.async_get_options_flow(entry),
                    _fake_hass(unit),
                    "options",
                )
                result = await flow.async_step_init()
                obs.add_form(
                    "options.init",
                    _form(result, "init"),
                    [(cover_type, climate, unit)],
                )


class _FakeServices:
    def __init__(self) -> None:
        self.registered: dict[str, tuple[Any, Any]] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return False

    def async_register(self, domain, service, handler, schema=None, **_kw) -> None:
        self.registered[service] = (handler, schema)


class _FakeFlowManager:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def async_init(self, domain, *, context=None, data=None):
        self.created.append(data)
        return {"result": SimpleNamespace(entry_id="spec-parity", title="x")}


async def _walk_services(obs: Observations) -> None:
    """change_settings / add_entry schemas and the add_entry baseline."""
    from custom_components.adaptive_cover import _async_register_services

    for unit in UNITS:
        ctx = _contexts(units=[unit])
        services = _FakeServices()
        flows = _FakeFlowManager()
        hass = _fake_hass(
            unit,
            services=services,
            config_entries=SimpleNamespace(
                flow=flows, async_entries=lambda *_a, **_kw: []
            ),
        )
        _async_register_services(hass)
        for name in ("change_settings", "add_entry"):
            _handler, schema = services.registered[name]
            for marker, validator in schema.schema.items():
                described = describe(validator)
                described["required"] = isinstance(marker, vol.Required)
                obs.add_field(name, str(marker.schema), described, ctx)
            # Sorted: a service schema's key order is not user-visible (the
            # HA service UI renders services.yaml, not the schema).
            obs.forms[name].update(
                {c: tuple(sorted(str(m.schema) for m in schema.schema)) for c in ctx}
            )

        # The baseline an entry gets from add_entry without copy_from.
        handler, _schema = services.registered["add_entry"]
        await handler(SimpleNamespace(data={"name": "Spec parity", "cover": "cover.x"}))
        (created,) = flows.created
        baseline = dict(created["options"])
        # the cover argument (both keys), not a default
        baseline.pop("group", None)
        baseline.pop("cover_entity_id", None)
        for key, value in baseline.items():
            obs.add_field("add_entry.baseline", key, {"default": _num(value)}, ctx)
        obs.forms["add_entry.baseline"].update(
            {c: tuple(sorted(baseline)) for c in ctx}
        )


def _walk_services_yaml(obs: Observations) -> None:
    """The service field selectors the HA UI shows (services.yaml)."""
    data = yaml.safe_load((PACKAGE_DIR / "services.yaml").read_text(encoding="utf-8"))
    ctx = _contexts()
    for service in ("change_settings", "add_entry"):
        fields = data[service]["fields"]
        place = f"services_yaml.{service}"
        for key, field in fields.items():
            described: dict[str, Any] = (
                describe(selector.selector(field["selector"]))
                if field.get("selector")
                else {"kind": "none"}
            )
            described["required"] = bool(field.get("required", False))
            obs.add_field(place, key, described, ctx)
        obs.forms[place].update({c: tuple(fields) for c in ctx})


async def _walk_numbers(obs: Observations) -> None:
    """The live number entities, per cover type, climate mode and unit."""
    from custom_components.adaptive_cover import number as number_platform

    for unit in UNITS:
        for cover_type in COVER_TYPES:
            for climate in CLIMATES:
                entry = SimpleNamespace(
                    entry_id="spec-parity",
                    title="Spec parity",
                    data={"name": "Spec parity", "sensor_type": cover_type},
                    options={"climate_mode": climate == "on"},
                    runtime_data=SimpleNamespace(),  # the window's coordinator
                )
                hass = _fake_hass(unit)
                added: list[Any] = []
                await number_platform.async_setup_entry(hass, entry, added.extend)
                order = []
                for entity in added:
                    key = entity.unique_id.removeprefix(f"{entry.entry_id}_number_")
                    order.append(key)
                    described = _clean(
                        {
                            "kind": "number",
                            "min": entity.native_min_value,
                            "max": entity.native_max_value,
                            "step": entity.native_step,
                            "unit": entity.native_unit_of_measurement,
                            "mode": str(entity.mode),
                            "default": entity.native_value,
                        }
                    )
                    obs.add_field(
                        "number", key, described, [(cover_type, climate, unit)]
                    )
                # Sorted: creation order is not user-visible (HA lists a
                # device's entities by name).
                obs.forms["number"][(cover_type, climate, unit)] = tuple(sorted(order))


# ---------------------------------------------------------------- collapse


DIMENSIONS = (("types", COVER_TYPES), ("climate", CLIMATES), ("units", UNITS))


def _qualifier(contexts: set[Context]) -> str:
    """Name the contexts compactly, e.g. ``types=cover_blind; climate=on``.

    The contexts must form a product over the three dimensions (they do for
    every surface today); otherwise they are listed one by one.
    """
    axes = [sorted({ctx[i] for ctx in contexts}) for i in range(3)]
    product = {(t, c, u) for t in axes[0] for c in axes[1] for u in axes[2]}
    if product != contexts:
        return "contexts=" + ",".join("/".join(ctx) for ctx in sorted(contexts))
    parts = [
        f"{name}={'|'.join(values)}"
        for (name, universe), values in zip(DIMENSIONS, axes, strict=True)
        if tuple(values) != universe
    ]
    return "; ".join(parts)


def _where(place: str, contexts: set[Context]) -> str:
    qualifier = _qualifier(contexts)
    return f"{place} [{qualifier}]" if qualifier else place


def _group(by_context: dict[Context, Any]) -> list[tuple[Any, set[Context]]]:
    """Group contexts that share one value (values compared as JSON)."""
    groups: dict[str, tuple[Any, set[Context]]] = {}
    for ctx, value in by_context.items():
        token = json.dumps(value, sort_keys=True, ensure_ascii=False)
        groups.setdefault(token, (value, set()))[1].add(ctx)
    return sorted(groups.values(), key=lambda g: sorted(g[1]))


def collapse(obs: Observations) -> dict[str, Any]:
    """Turn observations into the committed JSON shape."""
    keys: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for (place, key), by_context in obs.fields.items():
        for described, contexts in _group(by_context):
            token = json.dumps(described, sort_keys=True, ensure_ascii=False)
            entry = keys[key].setdefault(token, {"where": [], **described})
            entry["where"].append(_where(place, contexts))
    keys_out = {
        key: sorted(
            ({**d, "where": sorted(d["where"])} for d in variants.values()),
            key=lambda d: d["where"],
        )
        for key, variants in sorted(keys.items())
    }
    forms_out: dict[str, list[str]] = {}
    for place, by_context in sorted(obs.forms.items()):
        for order, contexts in _group(by_context):
            forms_out[_where(place, contexts)] = list(order)
    return {
        "_about": (
            "Every settings surface: per option key, how each place describes "
            "it. Regenerate deliberately with `PYTHONPATH=. pixi run python "
            "tests/contract/generate_spec_parity.py`; the diff is the review "
            "artifact and needs a ledger entry (tests/contract/ledger.md)."
        ),
        "forms": dict(sorted(forms_out.items())),
        "keys": keys_out,
    }


async def build_snapshot() -> dict[str, Any]:
    """Walk every surface and return the snapshot (JSON-ready)."""
    obs = Observations()
    await _walk_setup(obs)
    await _walk_options(obs)
    await _walk_services(obs)
    _walk_services_yaml(obs)
    await _walk_numbers(obs)
    return collapse(obs)


def dumps(snapshot: dict[str, Any]) -> str:
    """Serialize the snapshot exactly as committed."""
    return json.dumps(snapshot, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def main() -> None:
    snapshot = asyncio.run(build_snapshot())
    SPEC_PARITY_PATH.write_text(dumps(snapshot), encoding="utf-8")
    print(
        f"Wrote {len(snapshot['keys'])} keys and {len(snapshot['forms'])} forms "
        f"to {SPEC_PARITY_PATH.relative_to(REPO_ROOT)}"
    )


if __name__ == "__main__":
    main()

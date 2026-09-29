"""Settings: the option spec and everything generated from it.

- ``spec.py``: one declarative row per option (pure data).
- ``schema.py``: wizard, options-form, service and number shapes built
  from the spec.
- ``validate.py``: cross-field checks.
- ``resolve.py``: one window's options from the house / floor / area /
  window layers (ADR 0003 precedence), with provenance (P5; pure).
- ``lift.py``: the migration that factors today's flat per-window options
  into those layers (P5; pure).
"""

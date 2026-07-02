"""Pure calculation engine for Adaptive Cover.

Everything in this package is pure: no Home Assistant imports, no wall-clock
reads, no entity access. Time, sun position, and climate readings enter as
explicit inputs; the output is a Decision carrying the position, the intent
that produced it, and a human-readable trace.

Enforced by tests/engine/test_purity.py.
"""

from .models import (
    BlindSpot,
    ClimateInputs,
    CoverConfig,
    Decision,
    GlareModel,
    Intent,
    Overhang,
    PositionLimits,
    SunSnapshot,
    TimeContext,
)
from .evaluate import evaluate

__all__ = [
    "BlindSpot",
    "ClimateInputs",
    "CoverConfig",
    "Decision",
    "GlareModel",
    "Intent",
    "Overhang",
    "PositionLimits",
    "SunSnapshot",
    "TimeContext",
    "evaluate",
]

"""
Shared fixtures for Phase 2 gate unit tests.
RFT-001 Phase 2 — Gate Unit Tests.
Updated RFT-003 Phase 3 — RunContext adapter for _gate_extension tests.
"""

import pytest
import sys
import os
from types import SimpleNamespace

# Ensure ibkr_purity_engine is importable from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


import sys
from unittest.mock import MagicMock

# Stub out heavy/optional dependencies so the engine module loads
# without them installed. Gate functions never use these.
for mod in ("ib_insync", "pandas_ta", "plotly", "plotly.graph_objects", "plotly.subplots"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


def build_extension_ctx(p):
    """Build a RunContext-compatible namespace from the old-style params dict.

    RFT-003 Phase 3: _gate_extension and _assess_tq_override now accept ctx
    instead of 20+ positional params. This adapter allows unit tests to
    continue using the flat params dict pattern while constructing the nested
    ctx.state structure required by the refactored signatures.

    Returns:
        tuple: (ctx, atr_dist, ext_limit) ready for _gate_extension(ctx, atr_dist, ext_limit)
    """
    state = SimpleNamespace(
        is_trending=p.get("is_trending", False),
        is_resolving=p.get("is_resolving", False),
        _entry_trending=p.get("_entry_trending", False),
        _entry_resolving=p.get("_entry_resolving", False),
        atr_raw=p.get("atr_raw", 2.0),
    )
    ctx = SimpleNamespace(
        state=state,
        p_code=p.get("p_code", "B"),
        is_etf=p.get("is_etf", False),
        last=p.get("last", {"close": 150.0}),
        resistance_raw=p.get("resistance_raw", 160.0),
        resistance_display=p.get("resistance_display", 160.0),
        _resistance_suppressed=p.get("_resistance_suppressed", False),
        floor_prox_pct=p.get("floor_prox_pct", 5.0),
        metrics=p.get("metrics", {}),
        # Fields consumed by _assess_tq_override (called from _gate_extension)
        adx_accel_state=p.get("adx_accel_state", "CRUISING"),
        adx_accel=p.get("adx_accel", 0.0),
        vol_confirm_state=p.get("vol_confirm_state", "MIXED"),
        vol_confirm_ratio=p.get("vol_confirm_ratio", 0.5),
        exit_signal=p.get("exit_signal", False),
        structural_floor_raw=p.get("structural_floor_raw", 140.0),
        price_scaler=p.get("price_scaler", 1.0),
        ext_limit=p.get("ext_limit", 1.0),
    )
    return ctx, p.get("atr_dist", 0.5), p.get("ext_limit", 1.0)


@pytest.fixture
def metrics():
    """Fresh empty metrics dict for each test."""
    return {}


@pytest.fixture
def extension_base_params():
    """Default passing state for _gate_extension.

    atr_dist well within limit, all override conditions neutral.
    Override only to change what you're testing.
    """
    return dict(
        atr_dist=0.5,
        ext_limit=1.0,
        p_code="B",
        is_etf=False,
        is_trending=True,
        is_resolving=False,
        _entry_trending=True,
        _entry_resolving=False,
        last={"close": 150.0, "open": 149.0, "SMA_200": 130.0},
        resistance_raw=160.0,
        resistance_display=160.0,
        _resistance_suppressed=False,
        floor_prox_pct=5.0,
        adx_accel_state="ACCELERATING",
        adx_accel=0.5,
        vol_confirm_state="STRONG INSTITUTIONAL",
        vol_confirm_ratio=0.8,
        exit_signal=False,
        structural_floor_raw=140.0,
        atr_raw=2.0,
        price_scaler=1.0,
        metrics={},
    )


@pytest.fixture
def capital_expectancy_base_params():
    """Default passing state for _gate_capital_expectancy (Profile A, risk >= 20% ATR)."""
    return dict(
        p_code="A",
        risk_a=1.0,           # >= 0.20 * atr_raw (0.4)
        cons_high_raw=160.0,
        last_close=150.0,
        hard_stop_raw=140.0,
        resistance_raw=165.0,
        atr_raw=2.0,
        price_scaler=1.0,
        metrics={},
    )

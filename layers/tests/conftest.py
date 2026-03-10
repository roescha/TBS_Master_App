"""Shared fixtures for TBS Purity Engine tests.

Provides:
    - metrics: empty metrics dict for gate unit tests
    - extension_base_params: default param dict for _gate_extension tests
    - build_extension_ctx: helper to construct (ctx, atr_dist, ext_limit) from params
    - capital_expectancy_base_params: default param dict for _gate_capital_expectancy tests

RFT-003 Phase 3 — conftest for RunContext-based gate tests.
RFT-003 Phase 4 — Added Phase 4 extraction function fixtures.
"""

try:
    import pytest
except ImportError:
    # Fallback for non-pytest environments (basic import validation)
    class _PytestStub:
        @staticmethod
        def fixture(fn):
            return fn
    pytest = _PytestStub()
from types import SimpleNamespace


# ── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def metrics():
    """Fresh empty metrics dict for each test."""
    return {}


# ── Extension gate helpers ───────────────────────────────────────────────────

@pytest.fixture
def extension_base_params():
    """Default parameters for _gate_extension tests.

    Returns a mutable dict. Tests override individual keys before
    calling build_extension_ctx(params).
    """
    return {
        "p_code": "B",
        "is_etf": False,
        "is_trending": True,
        "is_resolving": False,
        "_entry_trending": True,
        "_entry_resolving": False,
        "atr_dist": 0.5,
        "ext_limit": 1.0,
        "last": {"close": 150.0, "open": 149.0, "SMA_200": 130.0},
        "resistance_raw": 160.0,
        "resistance_display": 160.0,
        "_resistance_suppressed": False,
        "floor_prox_pct": 5.0,
        "metrics": {},
        "adx_accel_state": "CRUISING",
        "adx_accel": 0.0,
        "vol_confirm_state": "MIXED",
        "vol_confirm_ratio": 0.5,
        "exit_signal": False,
        "structural_floor_raw": 140.0,
        "price_scaler": 1.0,
        "atr_raw": 2.0,
    }


def build_extension_ctx(params):
    """Construct (ctx, atr_dist, ext_limit) from a params dict.

    Builds a SimpleNamespace that mimics RunContext for _gate_extension.
    Returns the 3-tuple that tests unpack.
    """
    state = SimpleNamespace(
        is_trending=params.get("is_trending", True),
        is_resolving=params.get("is_resolving", False),
        _entry_trending=params.get("_entry_trending", True),
        _entry_resolving=params.get("_entry_resolving", False),
        atr_raw=params.get("atr_raw", 2.0),
    )
    ctx = SimpleNamespace(
        state=state,
        p_code=params.get("p_code", "B"),
        is_etf=params.get("is_etf", False),
        last=params.get("last", {"close": 150.0, "open": 149.0, "SMA_200": 130.0}),
        resistance_raw=params.get("resistance_raw", 160.0),
        resistance_display=params.get("resistance_display", 160.0),
        _resistance_suppressed=params.get("_resistance_suppressed", False),
        floor_prox_pct=params.get("floor_prox_pct", 5.0),
        metrics=params.get("metrics", {}),
        adx_accel_state=params.get("adx_accel_state", "CRUISING"),
        adx_accel=params.get("adx_accel", 0.0),
        vol_confirm_state=params.get("vol_confirm_state", "MIXED"),
        vol_confirm_ratio=params.get("vol_confirm_ratio", 0.5),
        exit_signal=params.get("exit_signal", False),
        structural_floor_raw=params.get("structural_floor_raw", 140.0),
        price_scaler=params.get("price_scaler", 1.0),
        ext_limit=params.get("ext_limit", 1.0),
    )
    return ctx, params.get("atr_dist", 0.5), params.get("ext_limit", 1.0)


# ── Capital Expectancy gate helpers ──────────────────────────────────────────

@pytest.fixture
def capital_expectancy_base_params():
    """Default parameters for _gate_capital_expectancy tests.

    Returns a mutable dict whose keys match the function's keyword
    arguments.  Tests override individual keys before calling
    _gate_capital_expectancy(**p).

    Baseline: Profile A, risk_a=1.0 (above PE-CAL-2 threshold),
    last_close=150, hard_stop=140 → capital_risk=10,
    cons_high_raw=160 → capital_reward=10, cap_rr=1.0.
    """
    return {
        "p_code": "A",
        "risk_a": 1.0,
        "cons_high_raw": 160.0,
        "last_close": 150.0,
        "hard_stop_raw": 140.0,
        "resistance_raw": 165.0,
        "atr_raw": 2.0,
        "price_scaler": 1.0,
        "metrics": {},
    }

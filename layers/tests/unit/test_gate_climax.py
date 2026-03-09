"""Unit tests for _gate_climax.

RFT-001 Phase 2 — Gate Unit Tests.
"""

import pytest
import pandas as pd
from ibkr_purity_engine import _gate_climax, check_climax_history


def _make_climax_df(bars=10, climax_at=None):
    """Build a minimal DataFrame for climax testing.

    Parameters
    ----------
    bars : int
        Number of rows.
    climax_at : int or None
        If set, the bar at this iloc index gets volume > 2x SMA9 and a negative close.
        All other bars are non-climax.
    """
    data = {
        "open": [100.0] * bars,
        "close": [101.0] * bars,  # positive by default
        "volume": [1000.0] * bars,
        "vol_sma_9": [1000.0] * bars,
    }
    df = pd.DataFrame(data)
    if climax_at is not None and 0 <= climax_at < bars:
        df.loc[climax_at, "volume"] = 3000.0  # > 2 * 1000
        df.loc[climax_at, "close"] = 99.0     # negative bar (close < open)
    return df


class TestGateClimax:
    """Tests for Gate 3 — Volume Climax."""

    def test_nominal_pass_no_climax(self, metrics):
        """No climax in window — gate passes."""
        df = _make_climax_df(bars=10)
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is None

    def test_nominal_fail_climax_recent(self, metrics):
        """Climax 2 bars ago (Profile B) — gate fires."""
        df = _make_climax_df(bars=10, climax_at=8)  # iloc[-2]
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "CLIMAX BLOCK" in result[1]

    def test_boundary_climax_at_window_edge(self, metrics):
        """Climax 3 bars ago (edge of 3-bar lookback) — gate fires."""
        df = _make_climax_df(bars=10, climax_at=7)  # iloc[-3]
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_climax_outside_window(self, metrics):
        """Climax 4 bars ago — outside 3-bar window, gate passes."""
        df = _make_climax_df(bars=10, climax_at=6)  # iloc[-4]
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is None

    def test_variant_reclaim_precedence(self, metrics):
        """Climax detected + is_reclaim=True — reclaim voided, diagnostic changes."""
        df = _make_climax_df(bars=10, climax_at=9)  # iloc[-1]
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=True,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "CLIMAX PRECEDENCE" in result[1]
        assert "Reclaim voided" in result[1]

    def test_variant_profile_a_shifts_df(self, metrics):
        """Profile A — climax_df is df.iloc[:-1], shift the lookback by 1."""
        # Put climax at iloc[-2] of the FULL df → becomes iloc[-1] of climax_df
        df = _make_climax_df(bars=10, climax_at=8)  # iloc[-2] in full
        result = _gate_climax(
            df=df, p_code="A", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"

    def test_variant_profile_a_ago_offset(self, metrics):
        """Profile A ago += 1 — bars_ago reported is incremented for A."""
        df = _make_climax_df(bars=10, climax_at=8)
        result = _gate_climax(
            df=df, p_code="A", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        # Profile A adds 1 to ago: climax_df[-1] → ago=1 from check, +1 = 2
        assert "2 bars ago" in result[1]

    def test_vol_sma9_nan_rejects(self, metrics):
        """vol_sma_9 is NaN on last bar — data integrity rejection."""
        df = _make_climax_df(bars=10)
        df.loc[df.index[-1], "vol_sma_9"] = float("nan")
        result = _gate_climax(
            df=df, p_code="B", is_reclaim=False,
            check_climax_history_fn=check_climax_history, metrics=metrics,
        )
        assert result is not None
        assert result[0] == "HALT"
        assert "DATA INTEGRITY" in result[1]

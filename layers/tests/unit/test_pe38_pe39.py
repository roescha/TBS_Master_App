"""PE-38 + PE-39 Regression Tests.

PE-38: _evaluate_precheck preserve-and-merge guard — verifies that an existing
       EXIT signal from the exit dispatcher is not downgraded by precheck floor
       failure detection. Trigger labels are merged, not replaced.

PE-39: _gate_capital_expectancy Profile B transparency guard — verifies that
       Capital_Reward_Risk and Capital_RR_Label are suppressed to None when
       Exit_Signal == "EXIT" (reinforcing PE-7 suppression).

Tests use unittest.mock.patch to isolate the guard logic from the deep
dependency chain (_assess_floor_state, _evaluate_floor_failure_context,
_deep_reclaim_scan).
"""

import pytest
import pandas as pd
import numpy as np
from types import SimpleNamespace
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from tbs_engine.compute import _evaluate_precheck
from tbs_engine.gates import _gate_capital_expectancy


# ---------------------------------------------------------------------------
# Helpers: minimal DataFrame + ctx construction
# ---------------------------------------------------------------------------

def _make_precheck_df(n=60, base=100.0, anchor_offset=0.0):
    """Build a minimal DataFrame suitable for _evaluate_precheck.

    anchor_offset: positive = close above ANCHOR (normal), negative = below.
    """
    rng = np.random.RandomState(42)
    closes = [base + 0.2 * i + rng.normal(0, 0.1) for i in range(n)]
    df = pd.DataFrame({
        'open':   [c - 0.1 for c in closes],
        'high':   [c + 1.0 for c in closes],
        'low':    [c - 1.0 for c in closes],
        'close':  closes,
        'volume': [500000] * n,
    })
    df['ANCHOR'] = df['close'].rolling(20, min_periods=1).mean()
    df['SMA_50'] = df['close'].rolling(50, min_periods=1).mean()
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['SMA_200'] = df['close'].rolling(min(200, n - 1), min_periods=1).mean()
    df['ATRr_14'] = 2.0  # constant ATR for simplicity

    # Apply anchor offset to evaluated bar
    i0 = -1  # Profile B default
    df.iloc[i0, df.columns.get_loc('close')] = df['ANCHOR'].iloc[i0] + anchor_offset

    return df


def _make_ctx(df, p_code="B", metrics=None, exit_signal=False):
    """Build a minimal RunContext-like namespace for _evaluate_precheck."""
    if metrics is None:
        metrics = {}
    state = SimpleNamespace(
        atr_raw=2.0,
        is_floor_failure=False,
        consec_below=0,
        _reclaim_run=0,
        is_trending=True,
        is_resolving=False,
        adx_t=25.0,
        di_plus=20.0,
        di_minus=15.0,
    )
    cfg = SimpleNamespace(iq=-1)  # Profile B uses last bar
    last = df.iloc[cfg.iq]

    ctx = SimpleNamespace(
        state=state,
        cfg=cfg,
        df=df,
        last=last,
        p_code=p_code,
        metrics=metrics,
        price_scaler=1.0,
        hard_stop_raw=last['ANCHOR'] - 3.0,
        cons_high_raw=last['close'] + 10.0,
        exit_signal=exit_signal,
        _df_ctx=None,  # FFD-001 will be mocked
        risk_a=None,
        reward_a=None,
    )
    return ctx


def _make_floor_result(consec_below=5, current_above_floor=False,
                       is_floor_failure=True, is_violated=True, is_reclaim=False):
    """Build a mock return value for _assess_floor_state."""
    return SimpleNamespace(
        consec_below=consec_below,
        current_above_floor=current_above_floor,
        is_floor_failure=is_floor_failure,
        is_violated=is_violated,
        is_reclaim=is_reclaim,
    )


def _make_deep_reclaim_result(is_recent_failure=True, hist_below=4, reclaim_run=2):
    """Build a mock return value for _deep_reclaim_scan."""
    return SimpleNamespace(
        is_recent_failure=is_recent_failure,
        hist_below=hist_below,
        reclaim_run=reclaim_run,
    )


# ===========================================================================
# PE-38: _evaluate_precheck preserve-and-merge guard — SHALLOW SCAN
# ===========================================================================

class TestPE38_ShallowScan:
    """PE-38 guard tests for the shallow (is_floor_failure_pre) scan path."""

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_preserved_on_consolidation(self, mock_floor, mock_ffd):
        """Test 1: Existing EXIT preserved on CONSOLIDATION (shallow).

        When _exit_profile_b returns EXIT and precheck detects CONSOLIDATION,
        Exit_Signal must remain EXIT, not be downgraded to WARNING.
        Floor_Breach must be merged into existing triggers.
        """
        mock_floor.return_value = _make_floor_result(
            consec_below=5, current_above_floor=False,
            is_floor_failure=True, is_violated=True, is_reclaim=False
        )
        # CONSOLIDATION: _ffd_breach=True
        mock_ffd.return_value = (True, "CONSOLIDATION", [])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "EXIT",
            "Exit_Triggers": ["EMA_8_Counter_Exit"],
            "Exit_Reason": "EMA 8 counter threshold reached",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="EXIT")

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT", "EXIT must not be downgraded to WARNING"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"], "Original trigger preserved"
        assert "Floor_Breach" in metrics["Exit_Triggers"], "Floor_Breach merged"
        assert metrics["Exit_Reason"] == "EMA 8 counter threshold reached", "Original Exit_Reason preserved"
        assert "Floor_Failure_Reclaim" in metrics

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_preserved_on_structural_breakdown(self, mock_floor, mock_ffd):
        """Test 2: Existing EXIT preserved on STRUCTURAL_BREAKDOWN (shallow).

        When _exit_profile_b returns EXIT and precheck detects STRUCTURAL_BREAKDOWN,
        Exit_Signal remains EXIT and Floor_Failure_Override is merged.
        """
        mock_floor.return_value = _make_floor_result(
            consec_below=5, current_above_floor=False,
            is_floor_failure=True, is_violated=True, is_reclaim=False
        )
        # STRUCTURAL_BREAKDOWN: _ffd_breach=False
        mock_ffd.return_value = (False, "STRUCTURAL_BREAKDOWN (daily Golden Cross absent)", ["daily Golden Cross absent"])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "EXIT",
            "Exit_Triggers": ["SMA_200_Catastrophic"],
            "Exit_Reason": "Close below 200-SMA catastrophic level",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="EXIT")

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT", "EXIT preserved"
        assert "SMA_200_Catastrophic" in metrics["Exit_Triggers"], "Original trigger preserved"
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"], "Floor_Failure_Override merged"
        assert metrics["Exit_Reason"] == "Close below 200-SMA catastrophic level", "Original reason preserved"

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_warning_set_when_no_exit_consolidation(self, mock_floor, mock_ffd):
        """Test 3: WARNING set as normal when no pre-existing EXIT (CONSOLIDATION).

        Confirms the else branch is unchanged — precheck writes WARNING
        when exit dispatcher did not produce EXIT.
        """
        mock_floor.return_value = _make_floor_result(
            consec_below=5, current_above_floor=False,
            is_floor_failure=True, is_violated=True, is_reclaim=False
        )
        mock_ffd.return_value = (True, "CONSOLIDATION", [])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "WARNING",
            "Exit_Triggers": ["EMA_8_Convexity_Breach"],
            "Exit_Reason": "EMA 8 convexity breach",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="WARNING")

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "WARNING"
        assert metrics["Exit_Triggers"] == ["Floor_Breach"]
        assert "FLOOR BREACH" in metrics["Exit_Reason"]

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_set_when_no_exit_structural_breakdown(self, mock_floor, mock_ffd):
        """Test 4: EXIT set as normal when no pre-existing EXIT (STRUCTURAL_BREAKDOWN).

        Confirms the else branch correctly writes EXIT when precheck detects
        structural breakdown without a prior EXIT from the dispatcher.
        """
        mock_floor.return_value = _make_floor_result(
            consec_below=5, current_above_floor=False,
            is_floor_failure=True, is_violated=True, is_reclaim=False
        )
        mock_ffd.return_value = (False, "STRUCTURAL_BREAKDOWN (bearish DI)", ["bearish DI"])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": False,
            "Exit_Triggers": "None",
            "Exit_Reason": "None",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal=False)

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT"
        assert metrics["Exit_Triggers"] == ["Floor_Failure_Override"]
        assert "FLOOR FAILURE OVERRIDE" in metrics["Exit_Reason"]


# ===========================================================================
# PE-38: _evaluate_precheck preserve-and-merge guard — DEEP SCAN
# ===========================================================================

class TestPE38_DeepScan:
    """PE-38 guard tests for the deep scan (_deep_reclaim_scan) path.

    Deep scan fires when: not is_floor_failure_pre AND current_above_floor
    AND not is_violated_pre AND _drs_pre.is_recent_failure.
    """

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._deep_reclaim_scan')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_preserved_on_deep_consolidation(self, mock_floor, mock_drs, mock_ffd):
        """Test 5a: Deep scan CONSOLIDATION with existing EXIT → EXIT preserved."""
        # Shallow scan: no floor failure (so deep scan runs)
        mock_floor.return_value = _make_floor_result(
            consec_below=0, current_above_floor=True,
            is_floor_failure=False, is_violated=False, is_reclaim=False
        )
        # Deep scan finds recent failure
        mock_drs.return_value = _make_deep_reclaim_result(
            is_recent_failure=True, hist_below=4, reclaim_run=2
        )
        # CONSOLIDATION
        mock_ffd.return_value = (True, "CONSOLIDATION", [])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "EXIT",
            "Exit_Triggers": ["EMA_8_Counter_Exit"],
            "Exit_Reason": "EMA 8 counter threshold reached",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="EXIT")

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT", "EXIT preserved on deep CONSOLIDATION"
        assert "EMA_8_Counter_Exit" in metrics["Exit_Triggers"]
        assert "Floor_Breach" in metrics["Exit_Triggers"], "Floor_Breach merged"
        assert metrics["Exit_Reason"] == "EMA 8 counter threshold reached"

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._deep_reclaim_scan')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_preserved_on_deep_structural_breakdown(self, mock_floor, mock_drs, mock_ffd):
        """Test 5b: Deep scan STRUCTURAL_BREAKDOWN with existing EXIT → EXIT preserved."""
        mock_floor.return_value = _make_floor_result(
            consec_below=0, current_above_floor=True,
            is_floor_failure=False, is_violated=False, is_reclaim=False
        )
        mock_drs.return_value = _make_deep_reclaim_result(
            is_recent_failure=True, hist_below=5, reclaim_run=1
        )
        mock_ffd.return_value = (False, "STRUCTURAL_BREAKDOWN (bearish DI)", ["bearish DI"])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "EXIT",
            "Exit_Triggers": ["SMA_50_Breach"],
            "Exit_Reason": "Close below 50-SMA",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="EXIT")

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT", "EXIT preserved on deep STRUCTURAL_BREAKDOWN"
        assert "SMA_50_Breach" in metrics["Exit_Triggers"]
        assert "Floor_Failure_Override" in metrics["Exit_Triggers"], "Floor_Failure_Override merged"
        assert metrics["Exit_Reason"] == "Close below 50-SMA"

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._deep_reclaim_scan')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_warning_set_deep_consolidation_no_exit(self, mock_floor, mock_drs, mock_ffd):
        """Test 5c: Deep scan CONSOLIDATION without prior EXIT → WARNING set normally."""
        mock_floor.return_value = _make_floor_result(
            consec_below=0, current_above_floor=True,
            is_floor_failure=False, is_violated=False, is_reclaim=False
        )
        mock_drs.return_value = _make_deep_reclaim_result(
            is_recent_failure=True, hist_below=4, reclaim_run=2
        )
        mock_ffd.return_value = (True, "CONSOLIDATION", [])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": False,
            "Exit_Triggers": "None",
            "Exit_Reason": "None",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal=False)

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "WARNING"
        assert metrics["Exit_Triggers"] == ["Floor_Breach"]
        assert "FLOOR BREACH" in metrics["Exit_Reason"]

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._deep_reclaim_scan')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_exit_set_deep_structural_no_exit(self, mock_floor, mock_drs, mock_ffd):
        """Test 5d: Deep scan STRUCTURAL_BREAKDOWN without prior EXIT → EXIT set normally."""
        mock_floor.return_value = _make_floor_result(
            consec_below=0, current_above_floor=True,
            is_floor_failure=False, is_violated=False, is_reclaim=False
        )
        mock_drs.return_value = _make_deep_reclaim_result(
            is_recent_failure=True, hist_below=5, reclaim_run=1
        )
        mock_ffd.return_value = (False, "STRUCTURAL_BREAKDOWN (bearish DI)", ["bearish DI"])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": False,
            "Exit_Triggers": "None",
            "Exit_Reason": "None",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal=False)

        _result = _evaluate_precheck(ctx, _ff_threshold=3)
        result_status = _result.verdict if _result else None

        assert metrics["Exit_Signal"] == "EXIT"
        assert metrics["Exit_Triggers"] == ["Floor_Failure_Override"]
        assert "FLOOR FAILURE OVERRIDE" in metrics["Exit_Reason"]


# ===========================================================================
# PE-38: Edge case — no duplicate trigger on merge
# ===========================================================================

class TestPE38_NoDuplicateTrigger:
    """Verify that the merge guard does not add a duplicate trigger label."""

    @patch('tbs_engine.compute._evaluate_floor_failure_context')
    @patch('tbs_engine.compute._assess_floor_state')
    def test_no_duplicate_floor_breach(self, mock_floor, mock_ffd):
        """If Floor_Breach already in triggers, do not add again."""
        mock_floor.return_value = _make_floor_result(
            consec_below=5, current_above_floor=False,
            is_floor_failure=True, is_violated=True, is_reclaim=False
        )
        mock_ffd.return_value = (True, "CONSOLIDATION", [])

        df = _make_precheck_df()
        metrics = {
            "Exit_Signal": "EXIT",
            "Exit_Triggers": ["EMA_8_Counter_Exit", "Floor_Breach"],
            "Exit_Reason": "EMA 8 counter threshold reached",
        }
        ctx = _make_ctx(df, metrics=metrics, exit_signal="EXIT")

        _evaluate_precheck(ctx, _ff_threshold=3)

        assert metrics["Exit_Triggers"].count("Floor_Breach") == 1, "No duplicate Floor_Breach"


# ===========================================================================
# PE-39: _gate_capital_expectancy Profile B transparency guard
# ===========================================================================

class TestPE39_CapitalRRGuard:
    """PE-39 guard tests for Profile B Capital R:R suppression on EXIT."""

    def test_capital_rr_suppressed_on_exit(self):
        """Test 6: Capital R:R suppressed to None when Exit_Signal == EXIT."""
        metrics = {
            "Exit_Signal": "EXIT",
            "Capital_Reward_Risk": None,
            "Capital_RR_Label": None,
        }
        # Profile B, with valid reward and risk so computation would normally succeed
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=None,               # Not used for Profile B
            cons_high_raw=None,         # Not used for Profile B
            last_close=100.0,
            hard_stop_raw=90.0,         # risk = 10
            resistance_raw=120.0,       # reward = 20
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None, "Gate should not HALT"
        assert metrics["Capital_Reward_Risk"] is None, "Capital R:R suppressed on EXIT"
        assert metrics["Capital_RR_Label"] is None, "Capital RR Label suppressed on EXIT"

    def test_capital_rr_computed_when_no_exit(self):
        """Test 7: Capital R:R computed normally when Exit_Signal != EXIT."""
        metrics = {
            "Exit_Signal": False,
            "Capital_Reward_Risk": None,
            "Capital_RR_Label": None,
        }
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=None,
            cons_high_raw=None,
            last_close=100.0,
            hard_stop_raw=90.0,         # risk = 10
            resistance_raw=120.0,       # reward = 20, R:R = 2.0
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None, "Gate should not HALT"
        assert isinstance(metrics["Capital_Reward_Risk"], float), "Capital R:R is a float"
        assert metrics["Capital_Reward_Risk"] == 2.0, "R:R = reward/risk = 20/10"
        assert isinstance(metrics["Capital_RR_Label"], str), "Label is a string"
        assert metrics["Capital_RR_Label"] == "HEALTHY", "R:R 2.0 >= 1.5 → HEALTHY"

    def test_capital_rr_computed_on_warning(self):
        """Capital R:R still computed when Exit_Signal == WARNING (not EXIT)."""
        metrics = {
            "Exit_Signal": "WARNING",
            "Capital_Reward_Risk": None,
            "Capital_RR_Label": None,
        }
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=None,
            cons_high_raw=None,
            last_close=100.0,
            hard_stop_raw=90.0,
            resistance_raw=120.0,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None
        assert isinstance(metrics["Capital_Reward_Risk"], float), "R:R computed on WARNING"
        assert isinstance(metrics["Capital_RR_Label"], str), "Label computed on WARNING"

    def test_profile_a_unaffected(self):
        """PE-39 guard only applies to Profile B — Profile A path unchanged."""
        metrics = {
            "Exit_Signal": "EXIT",
            "Capital_Reward_Risk": None,
            "Capital_RR_Label": None,
        }
        # Profile A with valid reward/risk (risk_a >= 0.20 * atr_raw)
        result = _gate_capital_expectancy(
            p_code="A",
            risk_a=1.0,                 # >= 0.20 * 2.0 = 0.4
            cons_high_raw=120.0,
            last_close=100.0,
            hard_stop_raw=90.0,
            resistance_raw=120.0,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        # Profile A has its own gate logic — PE-39 does not touch it
        assert result is None  # No HALT for this R:R

    def test_profile_c_unaffected(self):
        """PE-39 guard only applies to Profile B — Profile C path unchanged."""
        metrics = {
            "Exit_Signal": "EXIT",
            "Capital_Reward_Risk": None,
            "Capital_RR_Label": None,
        }
        result = _gate_capital_expectancy(
            p_code="C",
            risk_a=None,
            cons_high_raw=None,
            last_close=100.0,
            hard_stop_raw=90.0,
            resistance_raw=120.0,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
        )
        assert result is None
        assert metrics["Capital_Reward_Risk"] is None, "Profile C always None"
        assert metrics["Capital_RR_Label"] is None, "Profile C always None"

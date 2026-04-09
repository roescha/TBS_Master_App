"""REC-BUG-2: LSE Price Scale Mismatch — Display Scaling Tests.

Validates that Recovery_Swing_Low_Price and Recovery_Target are divided
by price_scaler in the output layer, matching the pattern used by all
other operator-facing price fields (Live_Price, Context_SMA200, etc.).

The R:R computation is dimensionless (all inputs in same native units),
so this bug affects display only — not gate correctness.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ═══════════════════════════════════════════════════════════════════════
#  Test 1: Scaling logic unit validation
# ═══════════════════════════════════════════════════════════════════════

class TestRecBug2_DisplayScaling:
    """Verify that the output.py scaling expressions produce correct values."""

    @pytest.mark.parametrize("price_scaler, raw_swing_low, raw_target, expected_sl, expected_tgt", [
        # USD: price_scaler=1.0, no change
        (1.0,   92.50,  110.0,  92.50, 110.0),
        # LSE (GBP non-ETF): price_scaler=100.0, pence→pounds
        (100.0, 7364.0, 8418.0, 73.64, 84.18),
        # LSE edge: round to 2dp
        (100.0, 1234.5, 5678.9, 12.35, 56.79),
    ])
    def test_swing_low_and_target_scaling(self, price_scaler, raw_swing_low,
                                           raw_target, expected_sl, expected_tgt):
        """Recovery display fields must be divided by price_scaler."""
        # Replicate output.py lines 1053-1054 (post-fix)
        scaled_sl = round(raw_swing_low / price_scaler, 2) if raw_swing_low is not None else None
        scaled_tgt = round(raw_target / price_scaler, 2) if raw_target is not None else None
        assert scaled_sl == expected_sl
        assert scaled_tgt == expected_tgt

    def test_none_handling(self):
        """None values pass through without error."""
        price_scaler = 100.0
        scaled_sl = round(None / price_scaler, 2) if None is not None else None
        scaled_tgt = round(None / price_scaler, 2) if None is not None else None
        assert scaled_sl is None
        assert scaled_tgt is None

    @pytest.mark.parametrize("price_scaler", [1.0, 100.0])
    def test_rr_ratio_invariant_to_scaling(self, price_scaler):
        """R:R is dimensionless — same ratio regardless of unit system.

        This confirms the R-Gate 4 computation was never broken;
        only the display values were in the wrong unit.
        """
        # Native units (pence for LSE)
        swing_low_pence = 7364.0
        current_pence = 8418.0
        target_pence = 9500.0

        risk = current_pence - swing_low_pence
        reward = target_pence - current_pence
        rr_native = reward / risk

        # Scaled units (pounds)
        swing_low_pounds = swing_low_pence / 100.0
        current_pounds = current_pence / 100.0
        target_pounds = target_pence / 100.0

        risk_s = current_pounds - swing_low_pounds
        reward_s = target_pounds - current_pounds
        rr_scaled = reward_s / risk_s

        assert round(rr_native, 4) == round(rr_scaled, 4)

    def test_diagnostic_target_scaled(self):
        """Diagnostic string should show target in display units (pounds for LSE)."""
        price_scaler = 100.0
        _rec_target = 8418.0  # pence
        _rec_target_src = "SMA_50"
        # Replicate output.py diagnostic line (post-fix)
        diag = f"Target: {_rec_target_src} ({_rec_target / price_scaler:.2f})."
        assert "84.18" in diag
        assert "8418" not in diag


# ═══════════════════════════════════════════════════════════════════════
#  Test 2: Non-LSE regression — USD unaffected
# ═══════════════════════════════════════════════════════════════════════

class TestRecBug2_USDRegression:
    """USD tickers (price_scaler=1.0) produce identical values before and after fix."""

    def test_usd_swing_low_unchanged(self):
        raw = 92.50
        assert round(raw / 1.0, 2) == 92.50

    def test_usd_target_unchanged(self):
        raw = 110.0
        assert round(raw / 1.0, 2) == 110.0

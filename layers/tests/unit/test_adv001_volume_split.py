"""ADV-001: Average Daily Volume Display -- Share Volume + Dollar Volume Split.

Verifies that the engine produces two distinct volume metrics:
  - ADV_20 (avg_daily_volume): share volume, human-verifiable
  - ADV_20_Dollar (avg_daily_dollar_volume): dollar turnover, Gate 0 input

Zero gate/verdict/threshold impact. Gate 0 continues using dollar volume
via direct parameter -- never reads from the metrics dict.
"""

import pytest
from tbs_engine.transform import _transform_output, _flatten, MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action_summary(verdict="VALID"):
    if verdict == "VALID":
        return {
            "verdict": "VALID", "reason": "PULLBACK",
            "entry_strategy": {"entry_price": 142.0, "stop_loss": 140.0, "target": 160.0},
        }
    return {
        "verdict": "INVALID", "reason": "EXTENDED",
        "approaching": False,
        "action": "WAIT.", "context": "Test.",
    }


def _make_flat(adv_shares=2_500_000.0, adv_dollar=250_000_000.0):
    """Minimal flat metrics with both ADV fields populated."""
    return {
        "Price": 100.0,
        "Structural_Floor": 95.0,
        "Resistance": 110.0,
        "ADV_20": adv_shares,
        "ADV_20_Dollar": adv_dollar,
        "Is_ETF": False,
        "Convexity_Class": "C1",
        "ETF_Primary_Exchange": None,
        "ETF_Detection_Source": None,
        "Entry_Reference": 95.0,
        "Hard_Stop": 93.0,
        "Profit_Target": 110.0,
    }


# ---------------------------------------------------------------------------
# T1: Share volume appears as avg_daily_volume in grouped output
# ---------------------------------------------------------------------------

class TestShareVolumeMapping:

    def test_avg_daily_volume_is_share_volume(self):
        """avg_daily_volume must carry the share count, not dollar turnover."""
        r = _transform_output(_make_action_summary(), _make_flat(adv_shares=2_500_000.0))
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] == 2_500_000.0

    def test_avg_daily_volume_not_dollar(self):
        """Confirm avg_daily_volume is NOT the dollar figure."""
        r = _transform_output(
            _make_action_summary(),
            _make_flat(adv_shares=2_500_000.0, adv_dollar=250_000_000.0),
        )
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] != 250_000_000.0
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] == 2_500_000.0


# ---------------------------------------------------------------------------
# T2: Dollar volume appears as avg_daily_dollar_volume in grouped output
# ---------------------------------------------------------------------------

class TestDollarVolumeMapping:

    def test_avg_daily_dollar_volume_present(self):
        """New field avg_daily_dollar_volume must exist in trade_snapshot."""
        r = _transform_output(_make_action_summary(), _make_flat(adv_dollar=250_000_000.0))
        assert r["trade_quality"]["volume"]["avg_daily_dollar_volume"]["value"] == 250_000_000.0

    def test_dollar_volume_independent_of_share_volume(self):
        """The two metrics are independently sourced -- different values."""
        r = _transform_output(
            _make_action_summary(),
            _make_flat(adv_shares=1_000_000.0, adv_dollar=150_000_000.0),
        )
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] == 1_000_000.0
        assert r["trade_quality"]["volume"]["avg_daily_dollar_volume"]["value"] == 150_000_000.0


# ---------------------------------------------------------------------------
# T3: Both metrics present on INVALID (gate rejection) paths
# ---------------------------------------------------------------------------

class TestBothMetricsOnInvalidPath:

    def test_share_volume_on_invalid(self):
        r = _transform_output(_make_action_summary("INVALID"), _make_flat())
        assert "avg_daily_volume" in r["trade_snapshot"]
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] == 2_500_000.0

    def test_dollar_volume_on_invalid(self):
        r = _transform_output(_make_action_summary("INVALID"), _make_flat())
        assert "avg_daily_dollar_volume" in r["trade_quality"]["volume"]
        assert r["trade_quality"]["volume"]["avg_daily_dollar_volume"]["value"] == 250_000_000.0


# ---------------------------------------------------------------------------
# T4: Null handling -- both metrics None when flat keys absent
# ---------------------------------------------------------------------------

class TestNullHandling:

    def test_share_volume_none_when_missing(self):
        flat = _make_flat()
        del flat["ADV_20"]
        r = _transform_output(_make_action_summary(), flat)
        assert (r["trade_snapshot"]["avg_daily_volume"] is None or r["trade_snapshot"]["avg_daily_volume"].get("value") is None)

    def test_dollar_volume_none_when_missing(self):
        flat = _make_flat()
        del flat["ADV_20_Dollar"]
        r = _transform_output(_make_action_summary(), flat)
        assert (r["trade_quality"]["volume"]["avg_daily_dollar_volume"] is None or r["trade_quality"]["volume"]["avg_daily_dollar_volume"].get("value") is None)


# ---------------------------------------------------------------------------
# T5: ETF path -- both metrics present (same structure, different values)
# ---------------------------------------------------------------------------

class TestETFPath:

    def test_etf_both_metrics(self):
        flat = _make_flat(adv_shares=5_000_000.0, adv_dollar=500_000_000.0)
        flat["Is_ETF"] = True
        r = _transform_output(_make_action_summary(), flat)
        assert r["trade_snapshot"]["avg_daily_volume"]["value"] == 5_000_000.0
        assert r["trade_quality"]["volume"]["avg_daily_dollar_volume"]["value"] == 500_000_000.0
        assert r["trade_snapshot"]["classification"]["type"] == "ETF"


# ---------------------------------------------------------------------------
# T6: trade_snapshot key count and key set
# ---------------------------------------------------------------------------

class TestTradeSnapshotStructure:

    def test_key_count(self):
        """trade_snapshot must have expected keys after SNAP-001 restructuring."""
        r = _transform_output(_make_action_summary(), _make_flat())
        assert len(r["trade_snapshot"]) >= 7

    def test_key_set(self):
        r = _transform_output(_make_action_summary(), _make_flat())
        assert "price" in r["trade_snapshot"]
        assert "avg_daily_volume" in r["trade_snapshot"]
        assert "classification" in r["trade_snapshot"]


# ---------------------------------------------------------------------------
# T7: MAPPED_FLAT_KEYS includes both ADV keys
# ---------------------------------------------------------------------------

class TestMappingRegistry:

    def test_adv_20_in_mapped_keys(self):
        assert "ADV_20" in MAPPED_FLAT_KEYS

    def test_adv_20_dollar_in_mapped_keys(self):
        assert "ADV_20_Dollar" in MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# T8: _flatten round-trip preserves both metrics
# ---------------------------------------------------------------------------

class TestFlattenRoundTrip:

    def test_roundtrip_share_volume(self):
        flat_in = _make_flat(adv_shares=3_000_000.0, adv_dollar=300_000_000.0)
        r = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(r)
        assert flat_out["ADV_20"] == 3_000_000.0

    def test_roundtrip_dollar_volume(self):
        flat_in = _make_flat(adv_shares=3_000_000.0, adv_dollar=300_000_000.0)
        r = _transform_output(_make_action_summary(), flat_in)
        _, _, flat_out = _flatten(r)
        assert flat_out["ADV_20_Dollar"] == 300_000_000.0

"""DSP-003 regression pins: DQ-9 DAILY_HIGH row sources from
Daily_Cons_High_Pre_Override, with Resistance fallback.

Bug Register entry: DSP-003 (🔴 IDENTIFIED → 🟡 IMPLEMENTED after this fix).

Root cause: transform.py DQ-9 Tier 1 row was fed `Resistance` (hourly on
Profile A) but labelled `DAILY_HIGH` with desc "10-bar daily high from
context chart". Label/value mismatch on every Profile A DAILY_CTX path
(84.83 hourly vs 85.22 daily on the BRC reference case).

Fix: compute.py emits `Daily_Cons_High_Pre_Override` at the Tier 1
assignment site, before PE-41 / RWD-001 escalation and before the
BRK-001 MM override block. transform.py reads the new key for the
DAILY_HIGH row, with Resistance fallback for Profile B (primary ==
context, values coincide by construction) and Profile A
FALLBACK_HOURLY (df_ctx unavailable).

These tests pin the contract at the transform layer.
"""

import copy
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tbs_engine.transform import _transform_output
from tests.unit.test_transform_output_diag001 import (
    _make_full_flat_metrics,
    _valid_action_summary,
    _invalid_action_summary,
)


def _find_tier1(target_or_hierarchy):
    """Return the DAILY_HIGH entry from target.hierarchy, or None if absent.

    [BUGR-002] Accepts either a list (legacy — searches only that list) or a
    dict (partitioned target container — searches both hierarchy and
    cleared_levels siblings). On PE-41 WEEKLY escalation paths where
    current_price > Daily Tier 1, the DAILY_HIGH row is EXCEEDED and lives in
    target.cleared_levels post-partition; test sites that exercise that path
    must pass the target dict so the helper spans both siblings.
    """
    if isinstance(target_or_hierarchy, dict):
        candidates = []
        for key in ("hierarchy", "cleared_levels"):
            lst = target_or_hierarchy.get(key)
            if lst:
                candidates.extend(lst)
    elif target_or_hierarchy:
        candidates = target_or_hierarchy
    else:
        return None
    for entry in candidates:
        if entry.get("label") == "DAILY_HIGH":
            return entry
    return None


# -----------------------------------------------------------------------
# Profile A — DAILY_CTX path (BRC reference case)
# -----------------------------------------------------------------------

class TestDSP003DailyCtxPath:
    """On DAILY_CTX paths, DAILY_HIGH row value must equal target.source.price."""

    def _brc_like_metrics(self):
        """BRC-equivalent Profile A fixture: DAILY_CTX, no escalation, no BRK."""
        m = _make_full_flat_metrics(profile="A")
        # Reference case: daily Tier 1 = 85.22, hourly Resistance = 84.83
        m["Daily_Cons_High_Pre_Override"] = 85.22  # DSP-003 new key
        m["Cons_High"] = 85.22                     # matches Tier 1 (no override)
        m["Resistance"] = 84.83                    # hourly primary-frame (unchanged)
        m["Profit_Target"] = 85.22                 # consumer of cons_high_raw
        m["Profit_Target_Source"] = "DAILY_CTX"
        m["Price"] = 84.20
        m["BRK_Model_Active"] = False
        return m

    def test_tier1_row_value_equals_profit_target(self):
        """DAILY_HIGH row price == target.source.price on DAILY_CTX (the DSP-003 core fix)."""
        m = self._brc_like_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1 is not None, "DAILY_HIGH row must be present on DAILY_CTX path"
        assert tier1["price"] == 85.22, (
            f"DAILY_HIGH row must carry daily Tier 1 (85.22), "
            f"not hourly Resistance (84.83). Got {tier1['price']}."
        )

    def test_tier1_row_value_not_equal_to_hourly_resistance(self):
        """Defensive check: row must NOT carry the hourly Resistance value (the bug)."""
        m = self._brc_like_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1["price"] != m["Resistance"], (
            "DAILY_HIGH row must not carry hourly Resistance (regression guard)."
        )

    def test_tier1_escalation_winner_fires_on_daily_ctx(self):
        """escalation_winner = True on Tier 1 when daily high == profit target
        (DSP-003 consequence #2 resolved)."""
        m = self._brc_like_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1["escalation_winner"] is True, (
            "escalation_winner must fire on Tier 1 on DAILY_CTX paths "
            "(was structurally stuck at False pre-fix)."
        )

    def test_trade_snapshot_resistance_remains_hourly(self):
        """trade_snapshot.resistance.price must remain the hourly value
        (this field is correctly labelled primary-frame and must not change)."""
        m = self._brc_like_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        assert r["trade_snapshot"]["resistance"]["price"] == 84.83, (
            "trade_snapshot.resistance.price must remain hourly (primary-frame) "
            "— correctly labelled field, must not change."
        )

    def test_tier1_role_desc_matches_semantic(self):
        """role.desc still says '10-bar daily high from context chart' — label
        promise now matched by value."""
        m = self._brc_like_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert "daily" in tier1["role"]["desc"].lower()


# -----------------------------------------------------------------------
# Profile A — PE-41 WEEKLY escalation path
# -----------------------------------------------------------------------

class TestDSP003Pe41WeeklyEscalation:
    """On PE-41 WEEKLY paths, the DAILY_HIGH row must carry the pre-override
    daily Tier 1 (not the escalated weekly 50-bar value).

    This is the case Option (a)(i) would have broken — it would have
    fed the row the escalated weekly value while still labelling it
    DAILY_HIGH.
    """

    def _pe41_weekly_metrics(self):
        m = _make_full_flat_metrics(profile="A")
        # Daily Tier 1 = 90.0 (pre-override, preserved)
        # Weekly escalation = 105.0 (becomes target/Profit_Target after PE-41 fires)
        m["Daily_Cons_High_Pre_Override"] = 90.0
        m["Cons_High"] = 105.0           # PE-41 overwrote Cons_High to weekly
        m["Profit_Target"] = 105.0       # follows Cons_High
        m["Profit_Target_Source"] = "WEEKLY_RESISTANCE (price above daily range)"
        m["Resistance"] = 88.0           # hourly
        m["Price"] = 92.0                # above daily high, triggers PE-41
        m["BRK_Model_Active"] = False
        return m

    def test_tier1_row_carries_daily_not_weekly(self):
        """DAILY_HIGH row must carry 90.0 (pre-override daily Tier 1),
        not 105.0 (the escalated weekly value).

        [BUGR-002] PE-41 path: current_price (92.0) > Daily Tier 1 (90.0),
        so the DAILY_HIGH row is EXCEEDED and lives in target.cleared_levels
        post-partition (not target.hierarchy).
        """
        m = self._pe41_weekly_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"])
        assert tier1 is not None, "DAILY_HIGH row must still be present on PE-41 paths"
        assert tier1["price"] == 90.0, (
            f"DAILY_HIGH row must carry pre-override daily Tier 1 (90.0), "
            f"not escalated weekly value (105.0). Got {tier1['price']}."
        )

    def test_tier1_escalation_winner_false_on_pe41(self):
        """On PE-41 escalation, Tier 1 is NOT the winner; WEEKLY_HIGH is.

        [BUGR-002] DAILY_HIGH lives in target.cleared_levels on this path.
        """
        m = self._pe41_weekly_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"])
        assert tier1["escalation_winner"] is False, (
            "On PE-41 escalation, DAILY_HIGH must not claim escalation_winner — "
            "WEEKLY_HIGH is the escalated target."
        )

    def test_tier1_status_is_exceeded_when_price_above(self):
        """Current price (92.0) > daily Tier 1 (90.0) → status EXCEEDED.

        [BUGR-002] EXCEEDED rows live in target.cleared_levels post-partition
        (but retain their status field per §4.7).
        """
        m = self._pe41_weekly_metrics()
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"])
        assert tier1["status"] == "EXCEEDED"


# -----------------------------------------------------------------------
# Profile A — BRK-001 breakout-model-active path
# -----------------------------------------------------------------------

class TestDSP003Brk001MmOverride:
    """On BRK-001 breakout-model-active paths, compute.py overwrites Cons_High
    to the MM target. The DSP-003 fix uses Daily_Cons_High_Pre_Override
    (the pre-override daily Tier 1), NOT the post-override Cons_High, so
    the DAILY_HIGH row is not polluted by the MM value.

    Additionally, BRK-001 §4.5 scoping in transform.py line 1779–1795 is
    expected to handle retention based on whether the daily Tier 1 sits
    between entry and measured move.
    """

    def _brk_active_metrics_with_daily_above_price(self):
        """BRK active, daily Tier 1 (85.0) sits ABOVE current price (84.2)
        but BELOW MM target (87.21). Per BRK-001 §4.5, this is an
        intermediate level and should be retained in the hierarchy."""
        m = _make_full_flat_metrics(profile="A")
        m["Daily_Cons_High_Pre_Override"] = 85.0   # pre-override daily Tier 1
        m["Cons_High"] = 87.21                     # BRK-001 overrode to MM
        m["Profit_Target"] = 87.21
        m["Profit_Target_Source"] = "MEASURED_MOVE (post-breakout projection)"
        m["MM_Target"] = 87.21
        m["Resistance"] = 84.83                    # hourly (= new support)
        m["Price"] = 84.2
        m["BRK_Model_Active"] = True
        m["BRK_Model_Tag"] = "POST_BREAKOUT"
        m["BRK_New_Support"] = 84.83               # hourly — was the old 10-bar high
        return m

    def test_tier1_row_carries_pre_override_not_mm_when_retained(self):
        """When BRK-001 scoping retains the row, it must carry the pre-override
        daily Tier 1 (85.0), not the post-override MM value (87.21)."""
        m = self._brk_active_metrics_with_daily_above_price()
        r = _transform_output(_invalid_action_summary(), m)
        hierarchy = r["trade_setup"]["target"]["hierarchy"]
        tier1 = _find_tier1(hierarchy)
        # If retained, must carry the pre-override value
        if tier1 is not None:
            assert tier1["price"] == 85.0, (
                f"If DAILY_HIGH row is retained on BRK-001 path, it must carry "
                f"the pre-override daily Tier 1 (85.0), not the MM value (87.21). "
                f"Got {tier1['price']}."
            )
            # And must not accidentally equal the MM target
            assert tier1["price"] != m["MM_Target"], (
                "DAILY_HIGH row must not carry MM_Target value (regression guard)."
            )

    def test_mm_row_is_escalation_winner_on_brk_path(self):
        """On BRK-001 path, MEASURED_MOVE row must be the escalation_winner
        (per BRK-001 §4.5 spec excerpt) — pre-existing invariant, confirmed
        unchanged by DSP-003."""
        m = self._brk_active_metrics_with_daily_above_price()
        r = _transform_output(_invalid_action_summary(), m)
        hierarchy = r["trade_setup"]["target"]["hierarchy"] or []
        mm_entries = [e for e in hierarchy if e.get("label") == "MEASURED_MOVE"]
        if mm_entries:
            assert mm_entries[0]["escalation_winner"] is True, (
                "MEASURED_MOVE must be escalation_winner on BRK-001 paths."
            )

    def test_brk_scoping_excludes_row_when_daily_matches_new_support(self):
        """When daily Tier 1 numerically coincides with BRK_New_Support (rare
        coincidence case), existing scoping filter at transform.py:1784-1785
        correctly excludes the row."""
        m = self._brk_active_metrics_with_daily_above_price()
        # Force coincidence: daily Tier 1 == hourly new support
        m["Daily_Cons_High_Pre_Override"] = 84.83
        m["BRK_New_Support"] = 84.83
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1 is None, (
            "When daily Tier 1 coincides with new support (hourly), "
            "BRK-001 scoping at line 1784-1785 must exclude the DAILY_HIGH row."
        )


# -----------------------------------------------------------------------
# Fallback — Profile B and Profile A FALLBACK_HOURLY
# -----------------------------------------------------------------------

class TestDSP003Fallback:
    """When Daily_Cons_High_Pre_Override is absent (Profile B, where the key
    is not emitted) or None (Profile A FALLBACK_HOURLY), transform falls
    back to reading Resistance — preserving pre-DSP-003 behaviour on these
    paths.

    Profile B: Resistance ≡ daily 10-bar high by construction (primary
    frame == context frame), so the fallback is semantically correct.

    Profile A FALLBACK_HOURLY: df_ctx unavailable (degraded defensive
    branch); no daily Tier 1 to surface. Row carries hourly under daily
    label — same label/value mismatch as pre-fix, but scoped to this
    edge case.
    """

    def test_profile_b_fallback_when_key_absent(self):
        """Profile B: Daily_Cons_High_Pre_Override not emitted by compute.py.
        transform falls back to Resistance, which equals daily Tier 1 by
        construction on Profile B."""
        m = _make_full_flat_metrics(profile="B")
        # Emulate Profile B: key not present in metrics at all
        assert "Daily_Cons_High_Pre_Override" not in m, (
            "fixture precondition: Profile B does not emit the new key"
        )
        m["Resistance"] = 162.5       # Profile B: Resistance ≡ daily 10-bar high
        m["Profit_Target"] = 162.5
        m["Profit_Target_Source"] = "10_Bar_Resistance"
        m["Price"] = 158.0
        m["BRK_Model_Active"] = False
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1 is not None, "DAILY_HIGH row must render on Profile B"
        assert tier1["price"] == 162.5, (
            f"Profile B fallback: row must carry Resistance ({m['Resistance']}). "
            f"Got {tier1['price']}."
        )

    def test_fallback_hourly_when_key_is_none(self):
        """Profile A FALLBACK_HOURLY: key explicitly set to None (compute.py:715).
        Fallback reads Resistance. Degraded-path behaviour, explicitly accepted."""
        m = _make_full_flat_metrics(profile="A")
        m["Daily_Cons_High_Pre_Override"] = None   # degraded Profile A path
        m["Resistance"] = 84.83                    # hourly (only reference available)
        m["Cons_High"] = 84.83                     # FALLBACK_HOURLY sets cons_high_raw to hourly
        m["Profit_Target"] = 84.83
        m["Profit_Target_Source"] = "FALLBACK_HOURLY (context data unavailable)"
        m["Price"] = 84.20
        m["BRK_Model_Active"] = False
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1 is not None
        assert tier1["price"] == 84.83, (
            "On FALLBACK_HOURLY, fallback to Resistance is the accepted degraded behaviour."
        )

    def test_row_suppressed_when_both_keys_none(self):
        """Edge case: both Daily_Cons_High_Pre_Override and Resistance are None
        (e.g., _resistance_suppressed branch in output.py:2094-2095). Row must
        be suppressed entirely."""
        m = _make_full_flat_metrics(profile="A")
        m["Daily_Cons_High_Pre_Override"] = None
        m["Resistance"] = None                     # suppressed (price above resistance)
        m["Profit_Target"] = 86.0
        m["Profit_Target_Source"] = "DAILY_CTX"
        m["Price"] = 85.0
        m["BRK_Model_Active"] = False
        r = _transform_output(_invalid_action_summary(), m)
        tier1 = _find_tier1(r["trade_setup"]["target"]["hierarchy"])
        assert tier1 is None, (
            "When both Daily_Cons_High_Pre_Override and Resistance are None, "
            "the DAILY_HIGH row must be suppressed (no row to emit)."
        )

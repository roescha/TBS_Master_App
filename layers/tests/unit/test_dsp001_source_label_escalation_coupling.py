"""DSP-001 / FRR-001-BUG-1 / CEG-002-BUG-1 — Source Label / Escalation Winner Coupling.

Spec: DSP001_Source_Label_Escalation_Coupling_Spec_v1_0.md (S142, v1.0)
Joint scope: DSP-001 + FRR-001-BUG-1 + CEG-002-BUG-1 (single fix in transform.py
resolves three bug-class siblings sharing the same mechanism).

Implements the eight test classes enumerated in spec §5.1:

    1. TestDsp001PltrCase                 — DSP-001 reference case (4 tests)
    2. TestFrr001Bug1SndkB                — winner in cleared_levels (2 tests)
    3. TestFrr001Bug1CrhB                 — analyst above DAILY_HIGH (1 test)
    4. TestCeg002Bug1BlueSky              — non-BRK blue-sky synthetic (1 test)
    5. TestBrkActiveNoOp                  — BRK skip clause regression (3 tests)
    6. TestNonBrkNoFundamentalNoCegNoOp   — preservation regression (2 tests)
    7. TestUnknownVocabularySafety        — fallback labels untouched (2 tests)
    8. TestHelperFunctionDirect           — _detect_source_tier unit tests (12)

Differential-evidence contract (spec §5.2):
    - Classes 1-4 MUST FAIL on pre-fix code (no re-derive block) and PASS on
      post-fix code. FAIL→PASS evidence captured in this session by
      temporarily reverting the transform.py §3.2 block, running the tests
      against the reverted source, then restoring and re-running. Result
      summary recorded in each class docstring below and in the standalone
      hand-back §3 (Phase 3 exit criterion).
    - Classes 5-7 are REGRESSION tests — they must pass both pre-fix and
      post-fix. They protect the BRK skip clause, the conceptually-matching
      preservation behaviour, and the unknown-vocabulary safety skip.
    - Class 8 is a direct unit test of the helper — it is not differential.

Architecture (spec §3.1, decision-owner authoritative):
    - BRK-active paths: compute.py owns the BRK target decision. The §4.2
      re-derive block skips entirely (`if not _brk_active`). Preserves
      LABEL-1, LABEL-2, OUT-002, BUGR-006 v2.0 work.
    - Non-BRK paths: transform.py's hierarchy escalation owns the "which
      tier wins by price match" decision. Re-derive when current
      source.label's detected tier differs from the escalation_winner tier.

Search scope (spec §2.6 / BUGR-002 §4.7): the re-derive block searches BOTH
target_hierarchy AND target_cleared_levels for the escalation_winner —
winners can land in cleared_levels on EXCEEDED paths (SNDK-B pattern-1).

Vocabulary mapping (spec §3.3 / §4.1):
    - "ANALYST"          → ANALYST_CONSENSUS
    - "ATR_PROJECTION"   → ATR_PROJECTION (substring or with space)
    - "MEASURED"         → MEASURED_MOVE
    - "WEEKLY"           → WEEKLY_HIGH
    - "PSYCH"            → PSYCHOLOGICAL
    - "RESISTANCE"       → DAILY_HIGH
    - "10_BAR"           → DAILY_HIGH
    - anything else      → None (skip re-derive for safety)

Import strategy
===============
Pure spec_from_file_location pattern with a non-package module name and no
sys.modules write — strictly equivalent to test_bugr002_hierarchy_partition.py.
transform.py has zero internal `from tbs_engine.X` imports (verified at spec
authoring time S142), so this approach is fully clean and avoids the
TEST-HRN-001 overwrite anti-pattern by construction (no module is registered
in sys.modules at all by this file).
"""

import os
import importlib.util as _ilu

import pytest


# ===========================================================================
# Pure safe-pattern transform.py loader
# ===========================================================================

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_TRANSFORM_PATH = os.path.join(_REPO_ROOT, "tbs_engine", "transform.py")

_t_spec = _ilu.spec_from_file_location(
    "tbs_engine_transform_dsp001",
    _TRANSFORM_PATH,
)
_transform_mod = _ilu.module_from_spec(_t_spec)
_t_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_detect_source_tier = _transform_mod._detect_source_tier


# ===========================================================================
# Verbatim label strings (cross-referenced from BUGR-006 v2.0 §4.3.3)
# ===========================================================================

LABEL_BRK_PRIMARY = "MEASURED_MOVE (BRK-001 post-breakout target)"
LABEL_BRK_WEEKLY_FALLBACK = "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_ATR_FALLBACK = "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_EXHAUSTED = "BRK-001 post-breakout (fallbacks exhausted)"

LABEL_ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
LABEL_BLUE_SKY_ATR = "ATR_PROJECTION (blue sky)"
LABEL_TECHNICAL_DEFAULT = "10_Bar_Resistance"
LABEL_WEEKLY_ANNOTATED = "WEEKLY_RESISTANCE (price above daily range)"
LABEL_FALLBACK_HOURLY = "FALLBACK_HOURLY (context data unavailable)"


# ===========================================================================
# Fixtures
# ===========================================================================

def _base_action_summary():
    """Minimal action_summary for _transform_output."""
    return {
        "verdict": "VALID",
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER",
        "context": "",
    }


def _base_flat_metrics(**overrides):
    """Minimal flat_metrics. Profile B by default. Tests override per-case."""
    m = {
        # Core
        "Price": 150.0,
        "Profit_Target": 156.28,
        "Profit_Target_Source": LABEL_TECHNICAL_DEFAULT,
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Profile_Code": "B",
        "BRK_Model_Active": False,

        # Hierarchy tier sources (default to populating only DAILY_HIGH)
        "Resistance": 156.28,
        "Daily_Cons_High_Pre_Override": 156.28,
        # Other tiers default to None (omitted from hierarchy)

        # Floor + risk
        "Floor_Anchor_Type": "SMA_50",
        "Floor_Anchor_Label": "Profile B daily floor",
        "Anchor_Label": "SMA_50",
        "Anchor_Type": "Standard",
        "Hard_Stop": 145.0,
        "Structural_Floor": 148.0,
        "ATR": 1.5,
        "Reward_Risk": 1.5,
        "Reward_Risk_Note": None,

        # Engine state — minimal
        "Engine_State": "MID-RANGE",
        "Engine_State_Desc": "",
        "ADX": 20.0,
        "DI_Plus": 20.0,
        "DI_Minus": 15.0,
    }
    m.update(overrides)
    return m


def _get_target(flat_overrides=None):
    """Run _transform_output and return trade_setup.target dict."""
    fm = _base_flat_metrics(**(flat_overrides or {}))
    return _transform_output(_base_action_summary(), fm)["trade_setup"]["target"]


# ===========================================================================
# 1. TestDsp001PltrCase — DSP-001 reference case
# ===========================================================================

class TestDsp001PltrCase:
    """[DSP-001] PLTR Profile B C-3 reference case — FRR-001 active, ANALYST
    tier in hierarchy with escalation_winner=False, DAILY_HIGH tier with
    escalation_winner=True.

    Differential evidence (spec §5.2): all four tests FAIL pre-fix (the §3.2
    re-derive block reverted) → PASS post-fix (block restored). Verified in
    S142 standalone session by temporary revert + re-run cycle.

    Pre-fix observed: source.label="ANALYST_CONSENSUS" (compute-layer write
    propagates verbatim through transform.py:1259 _target_obj construction).
    Post-fix observed: source.label="DAILY_HIGH" (re-derived from winner).
    """

    # PLTR shape: Profit_Target=156.28 matches DAILY_HIGH price; Fundamental_Target
    # at 200 above price; Profit_Target_Source = "ANALYST_CONSENSUS" from FRR-001.
    _PLTR = {
        "Price": 150.0,
        "Profit_Target": 156.28,
        "Profit_Target_Source": LABEL_ANALYST_CONSENSUS,
        "Profit_Target_Role": "INFORMATIONAL",  # FRR-001 demotion
        "Resistance": 156.28,
        "Daily_Cons_High_Pre_Override": 156.28,
        "Fundamental_Target": 200.00,
    }

    def test_source_label_redirected_to_winner_tier(self):
        """Spec §5.1 Class 1 test 1: source.label re-derives to "DAILY_HIGH"."""
        target = _get_target(self._PLTR)
        assert target["source"]["label"] == "DAILY_HIGH"
        # desc mirrors label per existing transform.py:1259 convention
        assert target["source"]["desc"] == "DAILY_HIGH"

    def test_profit_target_value_preserved(self):
        """Spec §5.1 Class 1 test 2: target.price unchanged by the fix."""
        target = _get_target(self._PLTR)
        assert target["price"] == 156.28

    def test_profit_target_role_preserved(self):
        """Spec §5.1 Class 1 test 3: FRR-001 INFORMATIONAL role preserved."""
        target = _get_target(self._PLTR)
        assert target["role"]["label"] == "INFORMATIONAL"

    def test_flat_key_audit_trail_preserved(self):
        """Spec §5.1 Class 1 test 4: flat-key Profit_Target_Source unchanged.

        Spec §3.2: the JSON-field target.source.label and the flat-key
        Profit_Target_Source are NOW SEPARATE concerns post-fix. The flat
        key retains compute-layer audit-trail semantics.
        """
        fm = _base_flat_metrics(**self._PLTR)
        # _transform_output does not mutate flat_metrics (verified by docstring
        # at transform.py:_transform_output: "Does NOT modify flat_metrics.")
        _transform_output(_base_action_summary(), fm)
        assert fm["Profit_Target_Source"] == LABEL_ANALYST_CONSENSUS


# ===========================================================================
# 2. TestFrr001Bug1SndkB — pattern-1 (winner in cleared_levels)
# ===========================================================================

class TestFrr001Bug1SndkB:
    """[FRR-001-BUG-1 pattern-1] SNDK-B — analyst median EXCEEDED, winner
    lands in target.cleared_levels (BUGR-002 §4.7 partition). Confirms the
    re-derive search scope spans BOTH hierarchy and cleared_levels.

    Differential evidence: both tests FAIL pre-fix → PASS post-fix.
    """

    # SNDK-B pattern-1 shape: Price=250, all targets exceeded → cleared_levels.
    # Profit_Target=156.28 matches DAILY_HIGH (in cleared, escalation_winner=True).
    # Fundamental_Target=200 also exceeded but not winner.
    # target_hierarchy is None (no targets above 250).
    _SNDK_B = {
        "Price": 250.0,
        "Profit_Target": 156.28,
        "Profit_Target_Source": LABEL_ANALYST_CONSENSUS,
        "Profit_Target_Role": "INFORMATIONAL",
        "Resistance": 156.28,
        "Daily_Cons_High_Pre_Override": 156.28,
        "Fundamental_Target": 200.00,
        "Hard_Stop": 230.0,
        "Structural_Floor": 240.0,
    }

    def test_winner_search_includes_cleared_levels(self):
        """Spec §5.1 Class 2 test 1: helper finds escalation_winner in
        target.cleared_levels when target_hierarchy has no winner.

        This is the BUGR-002 §4.7 case: forward array is empty/no-winner,
        winner is in cleared_levels.
        """
        target = _get_target(self._SNDK_B)
        # target_hierarchy should be None (everything is exceeded)
        assert target.get("hierarchy") is None
        # Winner lives in cleared_levels
        cl = target.get("cleared_levels") or []
        winners = [e for e in cl if e.get("escalation_winner")]
        assert len(winners) == 1
        assert winners[0]["label"] == "DAILY_HIGH"
        # And the re-derive picks up that winner
        assert target["source"]["label"] == "DAILY_HIGH"

    def test_source_label_redirected_when_winner_in_cleared_levels(self):
        """Spec §5.1 Class 2 test 2: source.label re-derived correctly."""
        target = _get_target(self._SNDK_B)
        assert target["source"]["label"] == "DAILY_HIGH"
        assert target["source"]["desc"] == "DAILY_HIGH"


# ===========================================================================
# 3. TestFrr001Bug1CrhB — pattern-2 (analyst above DAILY_HIGH)
# ===========================================================================

class TestFrr001Bug1CrhB:
    """[FRR-001-BUG-1 pattern-2] CRH-B — analyst median above DAILY_HIGH.
    Structurally identical to PLTR DSP-001 case, separate test class for
    bug-class traceability.

    Differential evidence: FAIL pre-fix → PASS post-fix.
    """

    _CRH_B = {
        "Price": 100.0,
        "Profit_Target": 110.50,
        "Profit_Target_Source": LABEL_ANALYST_CONSENSUS,
        "Profit_Target_Role": "INFORMATIONAL",
        "Resistance": 110.50,                  # DAILY_HIGH winner
        "Daily_Cons_High_Pre_Override": 110.50,
        "Fundamental_Target": 130.00,          # ANALYST tier above, not winner
        "Hard_Stop": 95.0,
        "Structural_Floor": 98.0,
    }

    def test_source_label_redirected_to_daily_high(self):
        """Spec §5.1 Class 3: source.label re-derives to "DAILY_HIGH"."""
        target = _get_target(self._CRH_B)
        assert target["source"]["label"] == "DAILY_HIGH"


# ===========================================================================
# 4. TestCeg002Bug1BlueSky — non-BRK Profile B blue-sky (synthetic)
# ===========================================================================

class TestCeg002Bug1BlueSky:
    """[CEG-002-BUG-1] Profile B non-BRK blue-sky path — same bug class on
    a different originating capability (CEG-002 instead of FRR-001).

    Synthetic fixture per spec §5.4 — live V-04 fixture acquisition deferred
    in standalone session (CEG-002 conjunction is structurally rare:
    resistance suppressed + compressed headroom + non-fundamental + ATR > 0).
    Mechanism-level coverage via this synthetic test.

    Differential evidence: FAIL pre-fix → PASS post-fix.
    """

    # CEG-002 shape: compute.py:968-969 wrote "ATR_PROJECTION (blue sky)"
    # but Profit_Target retained the technical default (output.py:2241) because
    # CEG-002's _early_capital_target is local — never written to
    # metrics["Profit_Target"]. So DAILY_HIGH wins by price match.
    _CEG_002 = {
        "Price": 100.0,
        "Profit_Target": 105.0,                          # matches DAILY_HIGH
        "Profit_Target_Source": LABEL_BLUE_SKY_ATR,      # the bug
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Resistance": 105.0,                              # DAILY_HIGH winner
        "Daily_Cons_High_Pre_Override": 105.0,
        "Blue_Sky_Target": 120.0,                         # ATR_PROJECTION tier @ 120, not winner
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
    }

    def test_atr_projection_label_redirected_when_winner_is_daily_high(self):
        """Spec §5.1 Class 4: source.label re-derives to "DAILY_HIGH" when
        CEG-002 wrote "ATR_PROJECTION (blue sky)" but Profit_Target retained
        the technical-default value.
        """
        target = _get_target(self._CEG_002)
        assert target["source"]["label"] == "DAILY_HIGH"
        # Audit-trail invariance check (spec §3.2): ATR_PROJECTION tier still
        # appears in the hierarchy with escalation_winner=False, preserving
        # the operator-visible record that the candidate existed.
        atr_entries = [
            e for e in target.get("hierarchy") or []
            if e["label"] == "ATR_PROJECTION"
        ]
        assert len(atr_entries) == 1
        assert atr_entries[0]["escalation_winner"] is False


# ===========================================================================
# 5. TestBrkActiveNoOp — REGRESSION protection of `if not _brk_active` clause
# ===========================================================================

class TestBrkActiveNoOp:
    """[REGRESSION] BRK-active paths must skip re-derive entirely. The
    `if not _brk_active:` clause at the top of the §4.2 re-derive block is
    the SINGLE guard preserving LABEL-1, LABEL-2, OUT-002, and BUGR-006 v2.0
    work (spec §6).

    These tests pass both pre-fix and post-fix — they protect against any
    future weakening of the BRK guard.
    """

    def test_brk_active_label_preserved_on_profile_a(self):
        """LABEL-2 verbatim Profile A BRK label preserved."""
        # Profile A BRK-active fixture. Construct a hierarchy where some
        # non-MM tier has escalation_winner=True — without the BRK skip the
        # re-derive would fire (LABEL "MEASURED_MOVE (BRK-001 ..." → MEASURED_MOVE
        # detected; if winner ≠ MEASURED_MOVE it would overwrite). With the
        # skip, the BRK label is preserved verbatim.
        target = _get_target({
            "Profile_Code": "A",
            "BRK_Model_Active": True,
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_BRK_PRIMARY,
            # Construct a non-MM winner — DAILY_HIGH @ 105 matches Profit_Target.
            # Pre-skip, helper would detect MEASURED_MOVE in source.label and
            # see winner=DAILY_HIGH → re-derive. The BRK skip prevents this.
            "Resistance": 105.0,
            "Daily_Cons_High_Pre_Override": 105.0,
            "Floor_Anchor_Type": "VWAP",
        })
        assert target["source"]["label"] == LABEL_BRK_PRIMARY

    def test_brk_active_label_preserved_on_profile_b(self):
        """BUGR-006 v2.0 Profile B BRK label preserved."""
        target = _get_target({
            "Profile_Code": "B",
            "BRK_Model_Active": True,
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_BRK_PRIMARY,
            "Resistance": 105.0,
            "Daily_Cons_High_Pre_Override": 105.0,
        })
        assert target["source"]["label"] == LABEL_BRK_PRIMARY

    def test_brk_active_with_frr_label_preserved(self):
        """BRK + fundamental conjunction — even with analyst data populated,
        the BRK label is preserved on BRK-active paths (LABEL-1 coexistence
        regression).
        """
        target = _get_target({
            "Profile_Code": "B",
            "BRK_Model_Active": True,
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_BRK_PRIMARY,
            "Resistance": 105.0,
            "Daily_Cons_High_Pre_Override": 105.0,
            "Fundamental_Target": 130.0,  # analyst data populated
        })
        assert target["source"]["label"] == LABEL_BRK_PRIMARY


# ===========================================================================
# 6. TestNonBrkNoFundamentalNoCegNoOp — preservation of correct labels
# ===========================================================================

class TestNonBrkNoFundamentalNoCegNoOp:
    """[REGRESSION] Conceptually-matching labels are preserved verbatim
    (spec §3.3): when the current source label's detected tier matches the
    winner tier, no re-derive fires.

    These tests pass both pre-fix and post-fix — they verify that the helper
    does not over-trigger and over-write correct labels.
    """

    def test_non_brk_resistance_label_preserved_when_winner_is_daily_high(self):
        """`"10_Bar_Resistance"` source label stays unchanged when DAILY_HIGH
        wins (helper detects RESISTANCE → DAILY_HIGH; matches winner; no
        re-derive).
        """
        target = _get_target({
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_TECHNICAL_DEFAULT,  # "10_Bar_Resistance"
            "Resistance": 105.0,
            "Daily_Cons_High_Pre_Override": 105.0,
        })
        # Helper detects RESISTANCE (and 10_BAR) → DAILY_HIGH; winner is
        # DAILY_HIGH; no re-derive.
        assert target["source"]["label"] == LABEL_TECHNICAL_DEFAULT

    def test_non_brk_weekly_label_preserved_when_winner_is_weekly_high(self):
        """`"WEEKLY_RESISTANCE (price above daily range)"` stays unchanged
        when WEEKLY_HIGH wins (helper detects WEEKLY → WEEKLY_HIGH; matches
        winner; no re-derive).

        Note (spec §2.3): WEEKLY_HIGH tier is added to the hierarchy ONLY
        when the source label contains the substring "WEEKLY". So this is
        an internally-consistent fixture by construction.
        """
        target = _get_target({
            "Price": 100.0,
            "Profit_Target": 110.0,
            "Profit_Target_Source": LABEL_WEEKLY_ANNOTATED,
            "Resistance": 105.0,                # DAILY_HIGH @ 105, not winner
            "Daily_Cons_High_Pre_Override": 105.0,
        })
        # WEEKLY_HIGH @ 110 added because "WEEKLY" in source label,
        # escalation_winner=True (always true on this tier per L1724).
        # Helper detects WEEKLY → WEEKLY_HIGH; winner is WEEKLY_HIGH; no
        # re-derive — annotated label preserved.
        assert target["source"]["label"] == LABEL_WEEKLY_ANNOTATED


# ===========================================================================
# 7. TestUnknownVocabularySafety — fallback labels untouched
# ===========================================================================

class TestUnknownVocabularySafety:
    """[REGRESSION] Helper returns None for unrecognised vocabulary; caller
    skips re-derive. Protects fallback labels (spec §3.3: "Cases skipped
    for safety").

    These tests pass both pre-fix and post-fix.
    """

    def test_brk_fallbacks_exhausted_label_unchanged(self):
        """`"BRK-001 post-breakout (fallbacks exhausted)"` is not modified —
        helper returns None (no substring match), caller skips re-derive.

        This label only appears on BRK-active paths in production (so the
        BRK skip would catch it first), but the helper-safety belt also
        covers it for defence in depth.
        """
        # Construct a non-BRK fixture with this label to isolate the helper-
        # safety branch. (Synthetic — does not occur in production on
        # non-BRK paths, but the safety check must still hold.)
        target = _get_target({
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_BRK_EXHAUSTED,
            "Resistance": 105.0,                  # DAILY_HIGH winner
            "Daily_Cons_High_Pre_Override": 105.0,
        })
        # _detect_source_tier returns None for "BRK-001 ..." → no re-derive
        assert target["source"]["label"] == LABEL_BRK_EXHAUSTED

    def test_fallback_hourly_label_unchanged(self):
        """`"FALLBACK_HOURLY (context data unavailable)"` not modified —
        helper returns None.
        """
        target = _get_target({
            "Price": 100.0,
            "Profit_Target": 105.0,
            "Profit_Target_Source": LABEL_FALLBACK_HOURLY,
            "Resistance": 105.0,
            "Daily_Cons_High_Pre_Override": 105.0,
        })
        assert target["source"]["label"] == LABEL_FALLBACK_HOURLY


# ===========================================================================
# 8. TestHelperFunctionDirect — _detect_source_tier unit tests
# ===========================================================================

class TestHelperFunctionDirect:
    """[UNIT] Direct tests on _detect_source_tier per spec §5.1 Class 8.

    Caller passes .upper() — these tests reflect that contract."""

    def test_analyst_detection(self):
        assert _detect_source_tier("ANALYST_CONSENSUS") == "ANALYST_CONSENSUS"

    def test_atr_projection_detection(self):
        # Underscore form (compute.py vocabulary)
        assert _detect_source_tier("ATR_PROJECTION") == "ATR_PROJECTION"
        # Annotated form (CEG-002 blue-sky write)
        assert _detect_source_tier("ATR_PROJECTION (BLUE SKY)") == "ATR_PROJECTION"

    def test_atr_projection_with_space(self):
        # Space form (defensive — vocabulary variant per spec §4.1)
        assert _detect_source_tier("ATR PROJECTION") == "ATR_PROJECTION"

    def test_measured_detection(self):
        assert _detect_source_tier("MEASURED_MOVE") == "MEASURED_MOVE"
        # BRK annotated form
        assert _detect_source_tier(
            "MEASURED_MOVE (BRK-001 POST-BREAKOUT TARGET)"
        ) == "MEASURED_MOVE"

    def test_weekly_detection(self):
        assert _detect_source_tier("WEEKLY_HIGH") == "WEEKLY_HIGH"
        assert _detect_source_tier(
            "WEEKLY_RESISTANCE (PRICE ABOVE DAILY RANGE)"
        ) == "WEEKLY_HIGH"

    def test_psych_detection(self):
        assert _detect_source_tier("PSYCHOLOGICAL") == "PSYCHOLOGICAL"

    def test_resistance_detection(self):
        assert _detect_source_tier("RESISTANCE") == "DAILY_HIGH"

    def test_10_bar_detection(self):
        # Caller passes .upper() — "10_Bar_Resistance".upper() = "10_BAR_RESISTANCE"
        assert _detect_source_tier("10_BAR_RESISTANCE") == "DAILY_HIGH"

    def test_unknown_returns_none(self):
        assert _detect_source_tier(
            "BRK-001 POST-BREAKOUT (FALLBACKS EXHAUSTED)"
        ) is None
        assert _detect_source_tier(
            "FALLBACK_HOURLY (CONTEXT DATA UNAVAILABLE)"
        ) is None
        assert _detect_source_tier("SOMETHING_RANDOM") is None

    def test_empty_returns_none(self):
        assert _detect_source_tier("") is None

    def test_none_returns_none(self):
        # Caller guards via `_current_label = _src.get("label") or ""`, so
        # a literal None never reaches the helper — but the body's first
        # check `if not source_label_upper:` handles None defensively.
        assert _detect_source_tier(None) is None

    def test_case_insensitive(self):
        # Helper expects an already-upper string; caller does .upper().
        # Verify the contract: lowercase input does NOT match (caller
        # responsibility to upper).
        assert _detect_source_tier("analyst_consensus") is None
        # And uppercase does match
        assert _detect_source_tier("ANALYST_CONSENSUS") == "ANALYST_CONSENSUS"

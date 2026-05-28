"""Tier 1R Display Hygiene Bundle — label hygiene tests.

Spec:  Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md (v1.0)
Brief: Tier_1R_Display_Hygiene_Bundle_Claude_Code_CLI_Implementation_Brief_v1_0.md

Covers the three constituent display-layer defects:

    DSP-004-OBS-1   Profile C extension_analysis.anchor.label/.desc weekly-frame
                    correctness (output.py:2873-2875 Profile C extension branch).
    DSP-004-OBS-2   Profile C floor_analysis.hierarchy[EMA_21].label weekly-frame
                    correctness + WEEKLY_EMA_21 vocabulary extension
                    (transform.py:3308-3314 _ema21_label_map + transform.py:176
                    _CONVICTION_TIER_MAP row).
    BUGR-006-LABEL-RESIDUAL-1
                    Idempotence guard substring widening "BRK-001 fallback" ->
                    "BRK-001" (output.py:2064-2066) — kills the double
                    parenthetical suffix on BRK-001 §8.1 MM-null fallback labels.

All three are display-layer cosmetic — zero gate / verdict / arithmetic impact
(spec §1.4).

Test class structure (spec §6.1 + Brief §6.1):

    1. TestDSP004OBS1ProfileCExtensionAnchorLabel
    2. TestDSP004OBS1ABRegressionInvariance
    3. TestDSP004OBS2ProfileCEMA21FloorEntryLabel
    4. TestDSP004OBS2OverheadLevelsPartition
    5. TestDSP004OBS2VocabularyExtension
    6. TestBUGR006LabelResidualGuardWidening
    7. TestBUGR006LabelResidualRegressionInvariance
    8. TestBundleVerdictInvariance
    9. TestBundleNotInGatesFile

Differential tests (spec §6.4) — FAIL pre-fix / PASS post-fix:

    TestDSP004OBS1ProfileCExtensionAnchorLabel::test_label_is_weekly_sma_200
    TestDSP004OBS1ProfileCExtensionAnchorLabel::test_desc_references_weekly_bars
    TestDSP004OBS2ProfileCEMA21FloorEntryLabel::test_label_is_weekly_ema_21
    TestDSP004OBS2OverheadLevelsPartition::test_overhead_partition_preserves_weekly_ema_21
    TestBUGR006LabelResidualGuardWidening::test_profile_b_brk_mm_null_weekly_fallback_single_suffix
    TestBUGR006LabelResidualGuardWidening::test_profile_b_brk_mm_null_atr_fallback_single_suffix

Construction / TEST-HRN-001 hygiene
===================================
transform.py has zero intra-package `from tbs_engine.X` imports, so it loads
cleanly via spec_from_file_location with a NON-package module name and NO
sys.modules registration (the TEST-HRN-001 safe pattern; mirrors
test_dsp004_profile_c_weekly_sma_label.py + test_bugr002_hierarchy_partition.py).
OBS-2 (transform.py edits) is therefore exercised fully behaviorally.

output.py transitively imports plotly via tbs_engine.charts and cannot be
loaded standalone in this environment; per the sanctioned
test_bugr006_label_fidelity_bundle.py (T-LABEL2-PB) precedent, output.py edits
(Edit 1 + Edit 4) are verified by SOURCE-INSPECTION. The BUGR-006 guard tests
go further than presence-checks: they REPLAY the idempotence guard predicate
extracted verbatim from output.py source against the real compute.py emission
strings — a source-driven behavioral differential. All source reads use
encoding="utf-8" (output.py contains §, ->, and em-dash glyphs post-edit).

Process Deviations (documented in Hand-Back §6)
===============================================
* TestBundleNotInGatesFile uses the spec §11.5 + Brief §4.7 identifier set
  (Extension_Anchor_Type, WEEKLY_EMA_21, WEEKLY_SMA_200, "BRK-001 fallback").
  DAILY_EMA_21 — listed in spec §6.1 — is EXCLUDED: it is a pre-existing
  Profile-A/B token used independently in REC-001 recovery-target construction
  (gates.py:1138, 1153), upstream of and untouched by this Bundle. Analyst
  direction received in-session (Option 1). See OBS-2/Vocab note below + §9 OI-1.
* Spec §3.3 lexicon / §4.3 / §11.4 / §6.1 name the module dict "_LABEL_TIER_MAP";
  the actual engine identifier is "_CONVICTION_TIER_MAP" (transform.py:165).
  Tests use the real name.
"""

import os
import re
import importlib.util

import pytest


# ===========================================================================
# Repo paths
# ===========================================================================

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENGINE_DIR = os.path.join(_REPO_ROOT, "tbs_engine")
_OUTPUT_PATH = os.path.join(_ENGINE_DIR, "output.py")
_TRANSFORM_PATH = os.path.join(_ENGINE_DIR, "transform.py")
_GATES_PATH = os.path.join(_ENGINE_DIR, "gates.py")


def _read_source(path):
    """Read an engine source file as UTF-8 (post-edit output.py carries §, ->,
    and em-dash glyphs that the Windows cp1252 default codec cannot decode)."""
    with open(path, encoding="utf-8") as f:
        return f.read()


# ===========================================================================
# Standalone transform.py loader (TEST-HRN-001 safe pattern)
# ===========================================================================
# Non-package module name, no sys.modules registration. transform.py has zero
# internal cross-imports so exec_module resolves cleanly.

_t_spec = importlib.util.spec_from_file_location(
    "tbs_engine_transform_dsp004_obs_bundle",
    _TRANSFORM_PATH,
)
_transform_mod = importlib.util.module_from_spec(_t_spec)
_t_spec.loader.exec_module(_transform_mod)

_transform_output = _transform_mod._transform_output
_CONVICTION_TIER_MAP = _transform_mod._CONVICTION_TIER_MAP


# ===========================================================================
# Verbatim compute.py BRK emission strings (spec §4.4) — character-for-character
# ===========================================================================

LABEL_BRK_PRIMARY = "MEASURED_MOVE (BRK-001 post-breakout target)"
LABEL_BRK_WEEKLY_FALLBACK = "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_ATR_FALLBACK = "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"
LABEL_BRK_EXHAUSTED = "BRK-001 post-breakout (fallbacks exhausted)"
# Profile A compute.py:774 prior-path form — already carries the suffix.
LABEL_PROFILE_A_PRIOR = "DAILY_CTX (BRK-001 fallback -- measured move unavailable)"

# The suffix the output.py guard appends when its substring is absent.
RESIDUAL_SUFFIX = " (BRK-001 fallback -- measured move unavailable)"


# ===========================================================================
# Fixtures (mirror test_dsp004_profile_c_weekly_sma_label.py shape)
# ===========================================================================

def _base_action_summary(verdict="VALID"):
    return {
        "verdict": verdict,
        "reason": {"label": "VALID PULLBACK", "detail": ""},
        "mandate": "ENTER" if verdict == "VALID" else "AVOID",
        "context": "",
    }


def _base_flat_metrics(**overrides):
    """Base flat_metrics with all hierarchy source values populated.

    Defaults to Profile A (Floor_Anchor_Type=EMA_21) with Price=130.0. Tests
    override Floor_Anchor_Type (profile selection per transform.py:3258-3267),
    the relevant MA values, and Price.
    """
    m = {
        "Price": 130.0,
        "Structural_Floor": 125.0,
        "Floor_Anchor_Type": "EMA_21",
        "Floor_Anchor_Label": "Intraday institutional value level",
        "Anchor_Label": "VWAP (Baseline Floor)",
        "Anchor_Type": "Standard",
        "Extension_Anchor_Type": "VWAP",
        "Extension_Anchor_Label": "Intraday institutional value level",
        "Hard_Stop": 120.0,
        "Resistance": 135.0,
        "EMA_8": 129.0,
        "EMA_21": 127.0,
        "SMA_50": 122.0,
        "SMA_200": 110.0,
        "VWAP": 126.0,
        "ATR": 2.5,
        "ADV_20": 5000000.0,
        "ADV_20_Dollar": 650000000.0,
        "Is_ETF": False,
        "Profit_Target": 135.0,
        "Profit_Target_Source": "10_Bar_Resistance",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "MM_Target": 140.0,
        "Blue_Sky_Target": 145.0,
        "Blue_Sky_Method": "ATR_PROJECTION",
        "Blue_Sky_Detected": True,
        "Fundamental_Target": 150.0,
        "Psych_Floor": 125.0,
        "Psych_Ceiling": 140.0,
        "Psych_Floor_Dist_Pct": 3.85,
        "Psych_Ceiling_Dist_Pct": 7.69,
        "Psych_Floor_Near_Structural": False,
        "Psych_Ceiling_Near_Technical": False,
        "Psych_Increment": 5.0,
        "RN_Target_Proximity": None,
        "RN_Stop_Proximity": None,
        "RN_Floor_Proximity": None,
        "Daily_Protective_Anchor": 128.0,
        "Daily_Hard_Stop": 124.0,
        "Daily_ATR": 3.0,
        "Context_EMA_21": 128.0,
        "Context_Daily_SMA50": 123.0,
        "Context_SMA200": 112.0,
        "AVWAP_Price": 127.5,
        "Established_Hourly_Low": 126.0,
        "Engine_State": "TRENDING",
        "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
        "ADX": 30.0,
        "ADX_Accel": 0.5,
        "ADX_Accel_State": "ACCELERATING",
        "DI_Plus": 25.0,
        "DI_Minus": 15.0,
        "DI_Spread": 10.0,
        "DI_Bias": "BULLISH",
        "Trend_Age_Bars": 5,
        "Trend_Age_Max": 20,
        "Active_Modifiers": "None",
        "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ATR_Dist": 0.8,
        "ATR_Dist_Anchor": "VWAP",
        "Extension_Limit": 1.5,
        "Trend_Health_Score": 65.0,
        "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 70.0,
        "THS_Dir_Momentum": 60.0,
        "THS_Trend_Age": 55.0,
        "THS_Structure": 50.0,
        "THS_Floor_Buffer_Label": "HEALTHY",
        "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age_Label": "ACCEPTABLE",
        "THS_Structure_Label": "ACCEPTABLE",
        "THS_Death_Cross_Cap": False,
        "THS_Component_Cap": None,
        "THS_VWAP_Floor_Penalty": False,
        "THS_VWAP_Floor_Note": None,
        "THS_Context_Advisory": None,
        "Vol_Confirm_Ratio": 1.2,
        "Vol_Confirm_State": "STRONG ACCUMULATION",
        "Vol_Confirm_Bias": "BULLISH",
        "Floor_Failure_Status_Label": "CLEAR",
        "Floor_Failure_Status_Desc": "No consecutive bars below structural floor",
        "Floor_Failure_Threshold": 8,
        "Exit_Signal": "HOLD",
        "window_count": 3,
        "Window_Limit": 4,
        "Window_Reset_Event": "PULLBACK",
        "Reward_Risk": 2.5,
        "Reward_Risk_Note": None,
        "Risk_Summary_Label": "FAVORABLE",
        "Risk_Summary_Desc": "Reward/Risk above 2.0 -- strong setup",
    }
    m.update(overrides)
    return m


def _profile_a_overrides():
    """Profile A: Floor_Anchor_Type in {VWAP, EMA_21}."""
    return {"Floor_Anchor_Type": "EMA_21"}


def _profile_b_overrides():
    """Profile B: Floor_Anchor_Type == SMA_50 (daily primary frame, no VWAP)."""
    return {
        "Floor_Anchor_Type": "SMA_50",
        "VWAP": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
    }


def _profile_c_overrides():
    """Profile C: Floor_Anchor_Type == SMA_200 (weekly primary frame per PA-001)."""
    return {
        "Floor_Anchor_Type": "SMA_200",
        "VWAP": None,
        "Daily_Protective_Anchor": None,
        "Daily_Hard_Stop": 0.0,
    }


# --- output helpers --------------------------------------------------------

def _stop(out):
    return out["trade_setup"]["stop"]


def _all_floor_entries(stop):
    entries = []
    for key in ("hierarchy", "overhead_levels"):
        v = stop.get(key)
        if v:
            entries.extend(v)
    return entries


def _labels(entries):
    return [e.get("label") for e in entries]


def _ema21_entry(stop):
    """Return (entry, partition_name) for the EMA-21-family floor entry, or
    (None, None). Identifies by the EMA_21 label family (DAILY/WEEKLY)."""
    for partition in ("hierarchy", "overhead_levels"):
        for e in (stop.get(partition) or []):
            if e.get("label") in ("DAILY_EMA_21", "WEEKLY_EMA_21"):
                return e, partition
    return None, None


def _extension_anchor_block(src):
    """Slice the output.py `Extension anchor` write block (between the
    `# Extension anchor:` marker and the `# --- FA-001` marker) so assertions
    target the extension dispatch and never the parallel Floor-anchor block."""
    start = src.index("# Extension anchor:")
    end = src.index("# --- FA-001", start)
    return src[start:end]


def _floor_anchor_block(src):
    """Slice the output.py Floor-anchor dispatch (from the Profile A Floor
    branch up to the `# Extension anchor:` marker)."""
    end = src.index("# Extension anchor:")
    start = src.rindex('metrics["Floor_Anchor_Type"]', 0, end)
    # Walk back to the start of the enclosing dispatch for context.
    start = src.rindex("if p_code ==", 0, start)
    return src[start:end]


# --- BUGR-006 residual-guard replay ----------------------------------------

def _residual_guard_parts():
    """Extract the idempotence-guard substring and the append suffix verbatim
    from output.py source. Single match each — the guard / append pair lives
    only at the Edit 4 site within output.py."""
    src = _read_source(_OUTPUT_PATH)
    guard_m = re.search(r'if\s+"([^"]+)"\s+not\s+in\s+str\(_existing_src\)\s*:', src)
    append_m = re.search(
        r'metrics\[\s*"Profit_Target_Source"\s*\]\s*=\s*str\(_existing_src\)\s*\+\s*"([^"]*)"',
        src,
    )
    assert guard_m is not None, "BUGR-006 idempotence guard not found in output.py"
    assert append_m is not None, "BUGR-006 append suffix not found in output.py"
    return guard_m.group(1), append_m.group(1)


def _apply_residual_guard(existing_src):
    """Replay the output.py guard semantics: append the fallback suffix only
    when the guard substring is absent. Faithful to output.py:2064-2066."""
    guard, suffix = _residual_guard_parts()
    s = str(existing_src)
    return s if guard in s else s + suffix


# ===========================================================================
# 1. TestDSP004OBS1ProfileCExtensionAnchorLabel
# ===========================================================================

class TestDSP004OBS1ProfileCExtensionAnchorLabel:
    """[DSP-004-OBS-1] Profile C extension anchor label + desc weekly-frame.

    Edit 1 lives in output.py `_populate_base_metrics` (transitively requires
    plotly), so the two differential tests verify the write site by
    source-inspection of the Profile-C extension branch; the surface
    propagation is confirmed behaviorally through transform.py.
    """

    @pytest.fixture(scope="class")
    def ext_block(self):
        return _extension_anchor_block(_read_source(_OUTPUT_PATH))

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_label_is_weekly_sma_200(self, ext_block):
        """Profile C extension anchor type is WEEKLY_SMA_200 (was SMA_200).

        FAIL pre-fix ('SMA_200'); PASS post-fix ('WEEKLY_SMA_200')."""
        assert 'metrics["Extension_Anchor_Type"] = "WEEKLY_SMA_200"' in ext_block, (
            "Profile C extension anchor must emit WEEKLY_SMA_200"
        )
        assert 'metrics["Extension_Anchor_Type"] = "SMA_200"' not in ext_block, (
            "bare 'SMA_200' extension anchor type must be gone from the "
            "extension dispatch post-fix"
        )

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_desc_references_weekly_bars(self, ext_block):
        """Profile C extension anchor desc references ~4 years on weekly bars
        (was ~10 months on daily bars).

        FAIL pre-fix ('...10 months on daily bars'); PASS post-fix."""
        assert (
            'metrics["Extension_Anchor_Label"] = '
            '"Long-term secular trend floor (~4 years on weekly bars)"'
        ) in ext_block, "Profile C extension anchor desc must reference weekly bars"
        assert "~10 months on daily bars" not in ext_block, (
            "stale daily-bars desc must be gone from the extension dispatch"
        )

    def test_extension_anchor_surface_propagates_weekly_value(self):
        """Behavioral (pass pre+post): transform surfaces whatever
        Extension_Anchor_Type/Label the base-metric layer wrote to
        extension_analysis.anchor — proving the weekly value reaches the JSON
        surface end-to-end once Edit 1 writes it."""
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=240.0,
            SMA_50=247.85,
            SMA_200=180.0,
            Extension_Anchor_Type="WEEKLY_SMA_200",
            Extension_Anchor_Label="Long-term secular trend floor (~4 years on weekly bars)",
        )
        out = _transform_output(_base_action_summary(), fm)
        anchor = out["extension_analysis"]["anchor"]
        assert anchor["label"] == "WEEKLY_SMA_200"
        assert "weekly bars" in anchor["desc"]

    def test_extension_label_desc_frame_agreement(self):
        """Behavioral (pass pre+post): when the weekly value is present, label
        and desc agree on the weekly frame (no DAILY/weekly cross-wiring)."""
        fm = _base_flat_metrics(
            **_profile_c_overrides(),
            Price=240.0,
            SMA_50=247.85,
            SMA_200=180.0,
            Extension_Anchor_Type="WEEKLY_SMA_200",
            Extension_Anchor_Label="Long-term secular trend floor (~4 years on weekly bars)",
        )
        out = _transform_output(_base_action_summary(), fm)
        anchor = out["extension_analysis"]["anchor"]
        assert "WEEKLY" in anchor["label"]
        assert "daily bars" not in anchor["desc"]

    def test_floor_anchor_branch_untouched(self):
        """Scope discipline (pass pre+post): Edit 1 must NOT bleed into the
        parallel Floor-anchor Profile C branch — it keeps SMA_200 / daily-bars
        desc (the Floor anchor is explicitly out of bundle scope, spec §4.1)."""
        floor_block = _floor_anchor_block(_read_source(_OUTPUT_PATH))
        assert 'metrics["Floor_Anchor_Type"] = "SMA_200"' in floor_block
        assert "~10 months on daily bars" in floor_block


# ===========================================================================
# 2. TestDSP004OBS1ABRegressionInvariance
# ===========================================================================

class TestDSP004OBS1ABRegressionInvariance:
    """[DSP-004-OBS-1] Profile A/B extension-anchor branches bitwise-invariant
    (the 5 non-Profile-C branches of the output.py extension dispatch)."""

    @pytest.fixture(scope="class")
    def ext_block(self):
        return _extension_anchor_block(_read_source(_OUTPUT_PATH))

    def test_profile_a_branch_unchanged(self, ext_block):
        assert 'metrics["Extension_Anchor_Type"] = "DAILY_EMA_21"' in ext_block
        assert (
            'metrics["Extension_Anchor_Label"] = '
            '"Daily protective anchor (~1 month on daily bars)"'
        ) in ext_block

    def test_profile_b_trending_branch_unchanged(self, ext_block):
        assert 'metrics["Extension_Anchor_Type"] = "EMA_21"' in ext_block
        assert (
            'metrics["Extension_Anchor_Label"] = '
            '"Medium-term trend support (~1 month on daily bars)"'
        ) in ext_block

    def test_profile_b_resolving_and_etf_branches_unchanged(self, ext_block):
        # RESOLVING short-momentum branch
        assert 'metrics["Extension_Anchor_Type"] = "EMA_8"' in ext_block
        # ETF Profile B branch + defensive else both keep SMA_50.
        assert 'metrics["Extension_Anchor_Type"] = "SMA_50"' in ext_block
        assert '"Intermediate institutional trend line"' in ext_block

    def test_profile_b_extension_surface_invariant(self):
        """Behavioral (pass pre+post): a non-Profile-C profile surfaces its
        Extension_Anchor_Type to extension_analysis.anchor unchanged."""
        fm = _base_flat_metrics(
            **_profile_b_overrides(),
            Price=140.0,
            SMA_50=130.0,
            Extension_Anchor_Type="EMA_21",
            Extension_Anchor_Label="Medium-term trend support (~1 month on daily bars)",
        )
        out = _transform_output(_base_action_summary(), fm)
        anchor = out["extension_analysis"]["anchor"]
        assert anchor["label"] == "EMA_21"
        assert "WEEKLY" not in anchor["label"]


# ===========================================================================
# 3. TestDSP004OBS2ProfileCEMA21FloorEntryLabel
# ===========================================================================

class TestDSP004OBS2ProfileCEMA21FloorEntryLabel:
    """[DSP-004-OBS-2] Profile C EMA 21 floor entry emits WEEKLY_EMA_21."""

    def _profile_c_holding(self):
        # Price above EMA 21 -> HOLDING -> hierarchy partition.
        return _base_flat_metrics(
            **_profile_c_overrides(),
            Price=245.0,
            Context_EMA_21=240.0,
            EMA_21=240.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_label_is_weekly_ema_21(self):
        """Profile C EMA 21 floor entry label is WEEKLY_EMA_21 (was DAILY_EMA_21).

        FAIL pre-fix ('DAILY_EMA_21'); PASS post-fix ('WEEKLY_EMA_21')."""
        out = _transform_output(_base_action_summary(), self._profile_c_holding())
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None, "expected an EMA 21 floor entry on Profile C"
        assert entry["label"] == "WEEKLY_EMA_21", (
            f"Profile C EMA 21 anchor must emit WEEKLY_EMA_21; got {entry['label']!r}"
        )

    def test_profile_a_ema21_retains_daily(self):
        """Regression-invariance (pass pre+post): Profile A keeps DAILY_EMA_21."""
        fm = _base_flat_metrics(**_profile_a_overrides(), Price=140.0,
                                Context_EMA_21=128.0, EMA_21=127.0)
        out = _transform_output(_base_action_summary(), fm)
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None
        assert entry["label"] == "DAILY_EMA_21"

    def test_profile_b_ema21_retains_daily(self):
        """Regression-invariance (pass pre+post): Profile B keeps DAILY_EMA_21."""
        fm = _base_flat_metrics(**_profile_b_overrides(), Price=140.0, EMA_21=130.0)
        out = _transform_output(_base_action_summary(), fm)
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None
        assert entry["label"] == "DAILY_EMA_21"

    def test_profile_c_ema21_role_desc_higher_frame(self):
        """Regression-invariance (pass pre+post): the Profile C role.desc already
        encoded the higher-frame asymmetry (_ema21_desc_map[C]); Edit 2 brings
        the LABEL into agreement with it — desc itself is unchanged."""
        out = _transform_output(_base_action_summary(), self._profile_c_holding())
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None
        assert "Higher-frame EMA 21" in entry["role"]["desc"]

    def test_profile_c_ema21_label_desc_frame_agreement(self):
        """Post-fix consistency (pass post): on Profile C the label is weekly
        AND the desc is higher-frame — they agree (the OBS-2 raison d'être)."""
        out = _transform_output(_base_action_summary(), self._profile_c_holding())
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None
        assert "WEEKLY" in entry["label"]
        assert "Higher-frame" in entry["role"]["desc"]


# ===========================================================================
# 4. TestDSP004OBS2OverheadLevelsPartition
# ===========================================================================

class TestDSP004OBS2OverheadLevelsPartition:
    """[DSP-004-OBS-2] BUGR-002 partition propagation — REL.L reproducer.

    Profile C with current price BELOW the EMA 21 anchor routes the entry to
    stop.overhead_levels[]; the WEEKLY_EMA_21 label must survive the partition.
    """

    def _profile_c_breached(self):
        # Price below EMA 21 -> BREACHED -> overhead_levels partition.
        return _base_flat_metrics(
            **_profile_c_overrides(),
            Price=240.0,
            Context_EMA_21=250.0,
            EMA_21=250.0,
            SMA_50=247.85,
            SMA_200=180.0,
        )

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_overhead_partition_preserves_weekly_ema_21(self):
        """EMA 21 entry below price lands in overhead_levels with WEEKLY_EMA_21.

        FAIL pre-fix ('DAILY_EMA_21' in overhead); PASS post-fix."""
        out = _transform_output(_base_action_summary(), self._profile_c_breached())
        overhead = _stop(out).get("overhead_levels") or []
        oh_labels = _labels(overhead)
        assert "WEEKLY_EMA_21" in oh_labels, (
            f"Profile C EMA 21 (above price) must route to overhead_levels with "
            f"label WEEKLY_EMA_21; got {oh_labels}"
        )
        assert "DAILY_EMA_21" not in oh_labels, (
            "Profile C overhead partition must not carry the daily label post-fix"
        )

    def test_ema21_routes_to_overhead_when_below_price(self):
        """Routing-by-price invariance (pass pre+post): regardless of label
        token, the EMA 21 entry partitions to overhead_levels when price is
        below it (partition predicate operates on price, not label)."""
        out = _transform_output(_base_action_summary(), self._profile_c_breached())
        entry, partition = _ema21_entry(_stop(out))
        assert entry is not None
        assert partition == "overhead_levels"

    def test_partition_preserves_conviction_tier(self):
        """Invariance (pass pre+post): the EMA 21 entry keeps MA_DYNAMIC rank 3
        across the partition — DAILY_EMA_21 and WEEKLY_EMA_21 both resolve there,
        so conviction is unchanged by the relabel (spec §4.2 behavior note)."""
        out = _transform_output(_base_action_summary(), self._profile_c_breached())
        entry, _ = _ema21_entry(_stop(out))
        assert entry is not None
        assert entry.get("conviction_tier") == "MA_DYNAMIC"
        assert entry.get("conviction_rank") == 3


# ===========================================================================
# 5. TestDSP004OBS2VocabularyExtension
# ===========================================================================

class TestDSP004OBS2VocabularyExtension:
    """[DSP-004-OBS-2] WEEKLY_EMA_21 vocabulary admitted at MA_DYNAMIC rank 3.

    NOTE: the engine dict is _CONVICTION_TIER_MAP (transform.py:165); spec §4.3
    calls it _LABEL_TIER_MAP — see module-docstring deviation + Hand-Back §6.
    """

    def test_weekly_ema_21_resolves_to_ma_dynamic_rank_3(self):
        """New vocabulary present post-Edit-3 (FAILs pre-fix — key absent; not
        among the named six but a genuine new-behavior assertion per spec §11.4)."""
        assert _CONVICTION_TIER_MAP.get("WEEKLY_EMA_21") == ("MA_DYNAMIC", 3)

    def test_daily_ema_21_resolution_unchanged(self):
        """Regression-invariance (pass pre+post): DAILY_EMA_21 still MA_DYNAMIC/3."""
        assert _CONVICTION_TIER_MAP.get("DAILY_EMA_21") == ("MA_DYNAMIC", 3)

    def test_weekly_sma_200_resolution_unchanged(self):
        """Regression-invariance (pass pre+post): WEEKLY_SMA_200 still MA_DYNAMIC/3
        (pre-existing token, unaffected by the OBS-1 extension-anchor relabel)."""
        assert _CONVICTION_TIER_MAP.get("WEEKLY_SMA_200") == ("MA_DYNAMIC", 3)


# ===========================================================================
# 6. TestBUGR006LabelResidualGuardWidening
# ===========================================================================

class TestBUGR006LabelResidualGuardWidening:
    """[BUGR-006-LABEL-RESIDUAL-1] Idempotence guard widening kills the double
    parenthetical suffix on BRK-001 §8.1 MM-null fallback labels.

    Tests replay the guard predicate extracted verbatim from output.py source
    against the real compute.py emission strings (source-driven differential).
    """

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_profile_b_brk_mm_null_weekly_fallback_single_suffix(self):
        """Weekly-fallback label keeps its single compute-layer parenthetical.

        FAIL pre-fix (guard 'BRK-001 fallback' misses '§8.1' form -> double
        suffix); PASS post-fix (guard 'BRK-001' matches -> no append)."""
        result = _apply_residual_guard(LABEL_BRK_WEEKLY_FALLBACK)
        assert result == LABEL_BRK_WEEKLY_FALLBACK, (
            f"guard must not append to the §8.1 weekly-fallback label; got {result!r}"
        )
        assert result.count("measured move unavailable") == 0

    # --- DIFFERENTIAL (spec §6.4) ---
    def test_profile_b_brk_mm_null_atr_fallback_single_suffix(self):
        """ATR-fallback label keeps its single compute-layer parenthetical.

        FAIL pre-fix (double suffix); PASS post-fix."""
        result = _apply_residual_guard(LABEL_BRK_ATR_FALLBACK)
        assert result == LABEL_BRK_ATR_FALLBACK, (
            f"guard must not append to the §8.1 ATR-fallback label; got {result!r}"
        )
        assert result.count("measured move unavailable") == 0

    def test_profile_b_brk_mm_null_exhausted_single_suffix(self):
        """Fallbacks-exhausted label is not double-appended (also flips FAIL->PASS,
        though not among the named six — guard 'BRK-001 fallback' missed it too)."""
        result = _apply_residual_guard(LABEL_BRK_EXHAUSTED)
        assert result == LABEL_BRK_EXHAUSTED, (
            f"guard must not append to the exhausted-fallback label; got {result!r}"
        )

    def test_profile_a_brk_mm_null_single_suffix(self):
        """Invariance (pass pre+post): the Profile A prior-path label already
        contains 'BRK-001 fallback', so BOTH the old and widened guards skip the
        append — Profile A stays clean either way (spec §4.4 behavior note)."""
        result = _apply_residual_guard(LABEL_PROFILE_A_PRIOR)
        assert result == LABEL_PROFILE_A_PRIOR
        assert result.count("measured move unavailable") == 1

    def test_guard_else_branch_writes_only_profit_target_source(self):
        """Verdict-neutrality (pass pre+post): the MM-null else branch touches
        only Profit_Target_Source — no verdict / gate / action_summary write —
        so widening the guard cannot perturb any verdict."""
        src = _read_source(_OUTPUT_PATH)
        # Isolate the MM-null else branch body (guard read -> guard -> append).
        anchor = src.index('_existing_src = metrics.get("Profit_Target_Source"')
        body = src[anchor:anchor + 1200]
        body = body[: body.index('# --- Entry reference override ---')]
        for forbidden in ('"verdict"', "gate_result", "action_summary",
                          '["Reward_Risk"]', '["Hard_Stop"]'):
            assert forbidden not in body, (
                f"guard else-branch unexpectedly references {forbidden!r}"
            )

    def test_guard_substring_is_brk_001(self):
        """Post-fix guard substring is the widened 'BRK-001' token (the whole
        single-token fix per spec §4.4 / DQ-4 Option α)."""
        guard, _ = _residual_guard_parts()
        assert guard == "BRK-001", f"expected widened guard 'BRK-001'; got {guard!r}"


# ===========================================================================
# 7. TestBUGR006LabelResidualRegressionInvariance
# ===========================================================================

class TestBUGR006LabelResidualRegressionInvariance:
    """[BUGR-006-LABEL-RESIDUAL-1] Paths unaffected by the guard widening."""

    def test_append_suffix_text_preserved_verbatim(self):
        """The appended suffix text is unchanged by Edit 4 (only the guard
        substring widened) — preserved for the legacy empty-source path."""
        _, suffix = _residual_guard_parts()
        assert suffix == RESIDUAL_SUFFIX

    def test_already_suffixed_source_not_double_appended(self):
        """A source already carrying 'BRK-001 fallback' is left untouched under
        BOTH the old and new guard — true regression-invariance."""
        already = "DAILY_CTX" + RESIDUAL_SUFFIX
        result = _apply_residual_guard(already)
        assert result == already
        assert result.count("measured move unavailable") == 1

    def test_mm_present_branch_label_write_unchanged(self):
        """Invariance (pass pre+post): the MM-present branch (`if _mm_raw is not
        None:`) is a SEPARATE code path from the guarded else branch and is
        untouched by Edit 4 — it still writes the standardized BRK primary label.
        (The guard else branch only runs on the MM-null path.)"""
        src = _read_source(_OUTPUT_PATH)
        assert (
            'metrics["Profit_Target_Source"] = "MEASURED_MOVE (BRK-001 post-breakout target)"'
            in src
        )

    def test_empty_source_gets_single_suffix(self):
        """Empty source -> single suffix under both guards (neither token present
        -> identical append). The legacy single-suffix path is preserved."""
        result = _apply_residual_guard("")
        assert result == RESIDUAL_SUFFIX
        assert result.count("measured move unavailable") == 1


# ===========================================================================
# 8. TestBundleVerdictInvariance
# ===========================================================================

class TestBundleVerdictInvariance:
    """[Bundle] verdict surface is unperturbed by the label edits (spec §1.4)."""

    def _profile_fixture(self, p_code, verdict):
        if p_code == "A":
            ov = dict(_profile_a_overrides(), Price=140.0, EMA_21=127.0)
        elif p_code == "B":
            ov = dict(_profile_b_overrides(), Price=140.0, SMA_50=130.0, EMA_21=130.0)
        else:
            ov = dict(_profile_c_overrides(), Price=240.0, EMA_21=250.0,
                      SMA_50=247.85, SMA_200=180.0)
        return _transform_output(_base_action_summary(verdict), _base_flat_metrics(**ov))

    def test_verdict_surface_valid_across_profiles(self):
        for p in ("A", "B", "C"):
            out = self._profile_fixture(p, "VALID")
            assert out["action_summary"]["verdict"] == "VALID", f"profile {p}"

    def test_verdict_surface_invalid_across_profiles(self):
        for p in ("A", "B", "C"):
            out = self._profile_fixture(p, "INVALID")
            assert out["action_summary"]["verdict"] == "INVALID", f"profile {p}"

    def test_profile_c_label_edits_do_not_perturb_verdict(self):
        """Invariance (pass pre+post): a Profile C run (the profile that carries
        all the bundle's relabels) surfaces the input verdict verbatim — the
        label edits never touch the verdict surface (spec §1.4)."""
        out_valid = self._profile_fixture("C", "VALID")
        assert out_valid["action_summary"]["verdict"] == "VALID"
        out_invalid = self._profile_fixture("C", "INVALID")
        assert out_invalid["action_summary"]["verdict"] == "INVALID"


# ===========================================================================
# 9. TestBundleNotInGatesFile
# ===========================================================================

class TestBundleNotInGatesFile:
    """[Bundle] Negative assertion — the bundle's changed/new identifiers do not
    appear in gates.py (zero gate impact, spec §5 / §11.5).

    Identifier set per spec §11.5 + Brief §4.7 (DAILY_EMA_21 EXCLUDED — see
    test_daily_ema_21_is_pre_existing_in_gates below + Hand-Back §6 / §9 OI-1)."""

    GATE_NEGATIVE_IDENTIFIERS = (
        "Extension_Anchor_Type",
        "WEEKLY_EMA_21",
        "WEEKLY_SMA_200",
        "BRK-001 fallback",
    )

    @pytest.fixture(scope="class")
    def gates_src(self):
        return _read_source(_GATES_PATH)

    def test_changed_identifiers_absent_from_gates(self, gates_src):
        present = [tok for tok in self.GATE_NEGATIVE_IDENTIFIERS if tok in gates_src]
        assert not present, (
            f"bundle identifiers must not appear in gates.py; found {present}"
        )

    def test_daily_ema_21_is_pre_existing_in_gates(self, gates_src):
        """Witness for the §6.1 deviation: DAILY_EMA_21 IS present in gates.py
        (REC-001 recovery-target construction) — pre-existing, Profile A/B,
        upstream of and untouched by this Bundle. This is why DAILY_EMA_21 is
        excluded from the gate-negative set above (spec §11.5 / Brief §4.7)."""
        assert "DAILY_EMA_21" in gates_src

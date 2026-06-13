"""OTL-001: Output Transformation Layer — Concept-Grouped JSON.

Pure mapping function that converts the flat (action_summary, metrics)
output into a concept-grouped dict. No computation, no conditionals beyond
null-checking, no gate logic.

Spec: OTL_001_Output_Mapping_Spec_v1_0.md + DIAG_001_Action_Summary_Spec_v1_0.md

Top-level reading order (operator cognitive sequence):
  1. action_summary           — "What happened?" (verdict, reason, mandate, context)
  2. trade_snapshot          — "What am I looking at?" (price, support, resistance)
  3. trade_quality           — "How good is it?"
  4. trade_risk              — "What's my risk exposure?"
  5. trend_state             — "What's the trend doing?"
  6. price_indicators        — "Where are the key levels?"
  7. floor_analysis          — "Is the floor intact?"
  8. trade_setup             — "What's the trade?"
  9. entry_proximity         — "Is an entry approaching?"
  10. exit_signals           — "Any position risk?"
  11. _debug (optional)      — Raw internals
"""


# ---------------------------------------------------------------------------
# Mapping tables
# Each entry: (flat_key, stripped_grouped_key)
# ---------------------------------------------------------------------------

# ===== TRADE_SNAPSHOT =====
# Explicit construction in _transform_output for operator readability:
#   current_price, support, resistance, avg_daily_volume, avg_daily_dollar_volume, classification{}
# DIAG-001 Phase 2B (DD-3): entry_strategy REMOVED — now in action_summary (VALID only)
# Classification sub-object: type (derived from Is_ETF), convexity, exchange, etf_detection

# SBO-001 Phase 2: Time-to-confirmation stop limit (mirrors output.py constant)
SBO_CONFIRMATION_BARS = 15

_GROUP_TRADE_SNAPSHOT_MAPPED = [
    ("Price",                  "current_price"),
    ("ADV_20",                 "avg_daily_volume"),
    ("ADV_20_Dollar",          "avg_daily_dollar_volume"),  # ADV-001
]

_GROUP_TRADE_SNAPSHOT_CLASSIFICATION = [
    ("Is_ETF",                 "is_etf"),
    ("Convexity_Class",        "convexity"),
    ("ETF_Primary_Exchange",   "exchange"),
    ("ETF_Detection_Source",   "etf_detection"),
]


# ===== TRADE_QUALITY =====
# THS-002: _TQ_TREND_HEALTH replaced with custom assembly in _transform_output
_TQ_TREND_HEALTH = []

# VOL-003: _TQ_VOLUME replaced with custom assembly in _transform_output
_TQ_VOLUME = []

# EXT-001: overextension_exception relocated to extension_analysis
_TQ_SCALARS = []

_TRADE_QUALITY_SUBGROUPS = [
    ("trend_health",    _TQ_TREND_HEALTH),
    ("volume",          _TQ_VOLUME),
]

# VOL-003 + EXT-001: 0 (trend_health custom) + 0 (volume custom) + 0 (scalars empty) = 0
_TQ_TOTAL = sum(len(t) for _, t in _TRADE_QUALITY_SUBGROUPS) + len(_TQ_SCALARS)
assert _TQ_TOTAL == 0


# ===== TRADE_RISK (custom assembly in _transform_output — RISK-001) =====

_GROUP_TRADE_RISK = []


# ===== TREND_STATE (custom assembly in _transform_output -- TS-001) =====

_TS_CLASSIFICATION = []

_TS_DIRECTIONAL = []

_TREND_STATE_SUBGROUPS = [
    ("classification",  _TS_CLASSIFICATION),
    ("directional",     _TS_DIRECTIONAL),
]

_TS_TOTAL = sum(len(t) for _, t in _TREND_STATE_SUBGROUPS)
assert _TS_TOTAL == 0


# ===== PRICE_INDICATORS (SNAP-001: absorbed into trade_snapshot.price_levels) =====

_GROUP_PRICE_INDICATORS = []


# ===== FLOOR_ANALYSIS (FA-001: custom assembly in _transform_output) =====

_GROUP_FLOOR_ANALYSIS_TOP = []

_HIGHER_FRAME_MAP = [
    ("Context_Golden_Cross",          "golden_cross"),
    ("Context_Price_vs_SMA200",       "price_vs_sma200"),
    ("Context_SMA200",                "sma200"),
    ("Context_Daily_SMA50",           "daily_sma50"),
    ("Context_Daily_SMA50_Slope",     "daily_sma50_slope"),
    # [EMA50-001] Profile A EMA 50 profile-specific keys
    ("Context_Daily_EMA_50",          "daily_ema_50"),
    ("Context_Daily_EMA_50_Slope",    "daily_ema_50_slope"),
    # [WKC-002] Profile A higher_frame (DAILY) stage classification
    ("Context_Daily_Stage_Classification", "daily_stage_classification"),
    ("Context_Weekly_Golden_Cross",   "golden_cross"),
    ("Context_Weekly_Price_vs_SMA200","price_vs_sma200"),
    ("Context_Weekly_SMA50",          "sma50"),
    ("Context_Weekly_SMA50_Slope",    "sma50_slope"),
    ("Context_Weekly_SMA50_Rising",   "sma50_rising"),
    # [WKC-002] Profile B higher_frame (WEEKLY) absolute SMA 200 + stage classification
    ("Context_Weekly_SMA200",         "sma200"),
    ("Context_Weekly_Stage_Classification", "weekly_stage_classification"),
    # [EMA50-001] Profile B EMA 50 profile-specific keys
    ("Context_Weekly_EMA_50",         "ema_50"),
    ("Context_Weekly_EMA_50_Slope",   "ema_50_slope"),
    ("Context_Monthly_Golden_Cross",  "golden_cross"),
    ("Context_Monthly_Price_vs_SMA200","price_vs_sma200"),
    ("Context_Monthly_SMA200",        "sma200"),
    ("Context_Monthly_SMA50",         "sma50"),
    ("Context_Monthly_SMA50_Slope",   "sma50_slope"),
    # [WKC-002] Profile C higher_frame (MONTHLY) stage classification
    ("Context_Monthly_Stage_Classification", "monthly_stage_classification"),
    # [EMA50-001] Profile C EMA 50 profile-specific keys
    ("Context_Monthly_EMA_50",        "ema_50"),
    ("Context_Monthly_EMA_50_Slope",  "ema_50_slope"),
]

_HIGHER_FRAME_ALL_KEYS = sorted(set(gk for _, gk in _HIGHER_FRAME_MAP))

# [WKC-001] Profile A weekly macro frame -- informational only, never a gate input.
# Surfaces under floor_analysis.macro_frame parallel to floor_analysis.higher_frame.
_MACRO_FRAME_MAP = [
    ("Context_Macro_SMA_50",          "sma50_price"),
    ("Context_Macro_SMA_50_Slope",    "sma50_slope"),
    ("Context_Macro_SMA_200",         "sma200_price"),
    ("Context_Macro_Golden_Cross",    "golden_cross_value"),
    ("Context_Macro_Price_vs_SMA200", "price_vs_sma200"),
    ("Context_Macro_EMA_8",           "ema8"),
    ("Context_Macro_EMA_21",          "ema21"),
    ("Context_Macro_EMA_Stacked",     "ema_stacked"),
    ("Context_Macro_EMA_50",          "ema50_price"),
    ("Context_Macro_EMA_50_Slope",    "ema50_slope"),
    ("Context_Macro_ADX",             "adx"),
    ("Context_Macro_Stage2",          "stage2_value"),
    ("Context_Macro_Stage2_Definition", "stage2_definition"),
    # WKC-001 v1.1: full Weinstein 4-stage classifier (replaces binary stage_2 semantically;
    # the boolean Context_Macro_Stage2 stays as derived backward-compat key)
    ("Context_Macro_Stage_Classification", "stage_classification"),
]
_MACRO_FRAME_ALL_KEYS = sorted(set(gk for _, gk in _MACRO_FRAME_MAP))


# [CNV-001] Conviction tier mapping for hierarchy entries.
# Static label-to-tier mapping. STRUCTURAL > PSYCHOLOGICAL > MA_DYNAMIC >
# PROJECTION > ATR_DERIVED > FUNDAMENTAL (rank 1 = highest conviction).
# Defensive default (None, None) on unrecognized labels — visible signal
# of value-space drift per CNV-001 spec DQ-5.
_CONVICTION_TIER_MAP = {
    # STRUCTURAL (rank 1) — horizontal-price history, market memory
    "ESTABLISHED_LOW": ("STRUCTURAL", 1),
    "DAILY_HIGH":      ("STRUCTURAL", 1),
    "WEEKLY_HIGH":     ("STRUCTURAL", 1),
    "NEW_SUPPORT":     ("STRUCTURAL", 1),
    # PSYCHOLOGICAL (rank 2) — round-number magnet
    "PSYCHOLOGICAL":   ("PSYCHOLOGICAL", 2),
    # MA_DYNAMIC (rank 3) — moving-average reference (daily + weekly per DSP-004 v1.1; weekly EMA 21 per DSP-004-OBS-2)
    "SESSION_VWAP":    ("MA_DYNAMIC", 3),
    "AVWAP_10BAR":     ("MA_DYNAMIC", 3),
    "DAILY_EMA_21":    ("MA_DYNAMIC", 3),
    "WEEKLY_EMA_21":   ("MA_DYNAMIC", 3),
    "DAILY_SMA_50":    ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_50":   ("MA_DYNAMIC", 3),
    "DAILY_SMA_200":   ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_200":  ("MA_DYNAMIC", 3),
    # PROJECTION (rank 4) — rally-leg / measured-move projection
    "MEASURED_MOVE":   ("PROJECTION", 4),
    # [ENG-006-OBS-1] Fibonacci extension rows are peers of the measured move
    # (role.label already "PROJECTION") — Addendum 1 §A3.1.
    "FIB_EXTENSION_1272": ("PROJECTION", 4),
    "FIB_EXTENSION_1618": ("PROJECTION", 4),
    "FIB_EXTENSION_2618": ("PROJECTION", 4),
    # ATR_DERIVED (rank 5) — synthetic ATR-buffered offset
    "HARD_STOP":         ("ATR_DERIVED", 5),
    "DAILY_HARD_STOP":   ("ATR_DERIVED", 5),
    "TIGHT_STOP":        ("ATR_DERIVED", 5),
    "CATASTROPHIC_STOP": ("ATR_DERIVED", 5),
    "ATR_PROJECTION":    ("ATR_DERIVED", 5),
    # FUNDAMENTAL (rank 6) — sell-side analyst consensus aggregation
    "ANALYST_CONSENSUS": ("FUNDAMENTAL", 6),
}


# [CFL-001] ATR-scaled adjacency thresholds for confluence detection.
# DQ-1 locked S157 — 0.25x floor (industry-tighter than the 0.5x TradingView
# default; stops are precision instruments) / 0.5x target (matches the
# TradingView S/R confluence indicator default). Both sides are calibration
# candidates after 3–6 months of live data — see CFL-001-CAL-1 (CONCEPT).
_CFL_FLOOR_THRESHOLD_ATR_MULT = 0.25
_CFL_TARGET_THRESHOLD_ATR_MULT = 0.5

# [CFL-001] Boundary tolerance for the inclusive `<=` comparison in the
# greedy adjacency walk. Absorbs IEEE-754 noise from `mult * atr` and
# `cur - prev`, both of which combine non-exact decimal floats. Sized
# at 1e-9 dollars -- 7 orders of magnitude below any plausible price
# quantum (penny = 1e-2), so it never causes a false-positive cluster
# at any operator-meaningful scale; ~4 orders of magnitude above the
# worst-case observed float drift (CRWD: diff - threshold = 1.05e-13).
# Added post-spec-v1.0 after a CRWD-A live-cohort run surfaced a near-
# miss where the displayed gap (2.01) equalled the displayed threshold
# (2.01) but underlying floats diverged by ~1e-13, causing the cluster
# to silently NOT form. Operator-confirmed addition.
_CFL_BOUNDARY_TOLERANCE = 1e-9

# [CFL-001] Side-aware strength-aware description templates per DQ-6.
# Format placeholders: {member_count}, {spread_atr}, {anchor_price}.
# Timing-neutral per SIR §10 — no "first test" or temporal predictions
# (CFL-001 has no knowledge of test history).
_CFL_STRENGTH_DESC_MAP = {
    ("floor", "MODERATE"):
        "MODERATE support cluster -- 2 anchors within {spread_atr} ATR of ${anchor_price}",
    ("floor", "STRONG"):
        "STRONG support cluster -- 3 anchors within {spread_atr} ATR of ${anchor_price}; institutional-grade convergence",
    ("floor", "EXCEPTIONAL"):
        "EXCEPTIONAL support cluster -- {member_count} anchors within {spread_atr} ATR of ${anchor_price}; rare multi-anchor convergence",
    ("target", "MODERATE"):
        "MODERATE resistance cluster -- 2 anchors within {spread_atr} ATR of ${anchor_price}",
    ("target", "STRONG"):
        "STRONG resistance cluster -- 3 anchors within {spread_atr} ATR of ${anchor_price}; institutional-grade convergence",
    ("target", "EXCEPTIONAL"):
        "EXCEPTIONAL resistance cluster -- {member_count} anchors within {spread_atr} ATR of ${anchor_price}; rare multi-anchor convergence",
}


def _annotate_conviction(entries):
    """CNV-001: tag each hierarchy entry with conviction_tier + conviction_rank.

    In-place mutation of the entries list. Unrecognized labels default to
    (None, None) per CNV-001 spec DQ-5 — visible signal of vocabulary drift.

    Returns the same list reference for chained-call ergonomics.
    """
    if not entries:
        return entries
    for _e in entries:
        _tier, _rank = _CONVICTION_TIER_MAP.get(_e.get("label"), (None, None))
        _e["conviction_tier"] = _tier
        _e["conviction_rank"] = _rank
    return entries


def _detect_level_confluence(entries, atr_value, threshold_mult, side):
    """CFL-001: detect adjacent-price clusters within (threshold_mult * ATR).

    In-place annotation of the entries list. Each entry that participates
    in a cluster (member_count >= 2) receives a `confluence` sub-object.
    Entries not in any cluster are left untouched — no `confluence` key
    is added. Absence of the field is silence (ordinary single-anchor
    strength), NOT a negative signal.

    Args:
        entries: hierarchy list. The greedy adjacent walk requires
            price-sorted input; the helper sorts a defensive local copy
            (ascending) so caller order is preserved on the entries list.
            Cluster identity is order-invariant.
        atr_value: current ATR(14) value from flat_metrics["ATR"].
        threshold_mult: 0.25 (floor side) or 0.5 (target side).
        side: "floor" or "target" — selects the desc template family.

    Returns:
        The same entries list reference (chained-call ergonomics, parallel
        to _annotate_conviction).

    Defensive behaviour (DQ-5):
        - empty entries -> no-op return
        - atr_value None / 0 / negative -> no-op return
        - entry with price=None -> excluded from clustering (the dict is
          left untouched)
    """
    if not entries or atr_value is None or atr_value <= 0:
        return entries

    threshold = threshold_mult * atr_value

    # Sort a local view by price (ascending). The greedy adjacent walk is
    # order-invariant on cluster identity, so ascending vs. descending does
    # not matter — but we must walk in some monotonic order. Caller's list
    # order is intentionally left untouched (BUGR-002 partition + sort
    # logic downstream depend on the caller-controlled order).
    _walk = sorted(
        (e for e in entries if e.get("price") is not None),
        key=lambda e: e["price"],
    )
    if len(_walk) < 2:
        return entries

    # `+ _CFL_BOUNDARY_TOLERANCE` makes the inclusive `<=` reliable at
    # the threshold even when float arithmetic introduces sub-penny noise.
    # See the constant's commentary above for the CRWD-A near-miss rationale.
    threshold_with_tolerance = threshold + _CFL_BOUNDARY_TOLERANCE

    clusters = []
    current_cluster = [_walk[0]]
    for entry in _walk[1:]:
        prev_price = current_cluster[-1]["price"]
        cur_price = entry["price"]
        if abs(cur_price - prev_price) <= threshold_with_tolerance:
            current_cluster.append(entry)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [entry]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    for cluster_idx, cluster in enumerate(clusters, start=1):
        member_count = len(cluster)
        if member_count == 2:
            strength = "MODERATE"
        elif member_count == 3:
            strength = "STRONG"
        else:  # >= 4
            strength = "EXCEPTIONAL"

        members = [m.get("label") for m in cluster]
        prices = [m["price"] for m in cluster]
        anchor_price = round(sum(prices) / len(prices), 2)
        spread_atr = round((max(prices) - min(prices)) / atr_value, 2)

        desc = _CFL_STRENGTH_DESC_MAP[(side, strength)].format(
            member_count=member_count,
            spread_atr=spread_atr,
            anchor_price=anchor_price,
        )

        confluence_obj = {
            "id": cluster_idx,
            "strength": strength,
            "member_count": member_count,
            "members": members,
            "desc": desc,
        }
        for m in cluster:
            m["confluence"] = confluence_obj

    return entries


# [PCT-001 OD-3] Profile A medium_term interpretation helper -- Operator
# scope extension post-Bundle 1 hand-back. Industry-convention bands for
# percentage distance from daily SMA 50; INFORMATIONAL only -- does NOT
# gate the verdict (DQ-8 retained: no `condition` / `thresholds` /
# `caution_note` siblings; only `interpretation` field added).
#
# Bands are general industry conventions (O'Neil / Minervini frameworks),
# not TBS-research-calibrated. A future Phase 4 reviewer can tighten with
# proper backtest data. Profile B retains its existing `condition` field
# with research-grounded thresholds.
def _derive_medium_term_interpretation(distance_pct):
    """Returns (label, desc) tuple from Profile A medium_term distance %.

    Returns (None, None) on None input.
    """
    if distance_pct is None:
        return (None, None)
    pct = distance_pct
    if pct < -5.0:
        return (
            "BELOW_SMA_50",
            "Price below daily SMA 50 -- unusual on Profile A; possible trend break or deep pullback.",
        )
    elif pct < 5.0:
        return (
            "HEALTHY",
            "Within normal trending range from daily SMA 50.",
        )
    elif pct < 10.0:
        return (
            "STRETCHED",
            "Stretched from daily SMA 50 but unremarkable in strong trends.",
        )
    elif pct < 15.0:
        return (
            "EXTENDED",
            "Extended from daily SMA 50; new entries closer to chasing than value-buying.",
        )
    elif pct < 20.0:
        return (
            "OVEREXTENDED",
            "Overextended from daily SMA 50; trim/short-setup zone for many names.",
        )
    elif pct < 30.0:
        return (
            "SIGNIFICANTLY_OVEREXTENDED",
            "Significantly overextended from daily SMA 50; high mean-reversion risk over next 2-6 weeks.",
        )
    else:
        return (
            "BLOW_OFF_ZONE",
            "Blow-off zone above daily SMA 50; very high reversal risk.",
        )


# ============================================================================
# [WKC-001 v1.1] Macro frame interpretation helpers.
# Used by the macro_frame emission block. All labels are derived at
# emission time from the underlying flat values; no new flat keys are
# introduced for the labels themselves (the underlying numeric values are
# already round-trippable via _MACRO_FRAME_MAP).
# ============================================================================

# WKC-001 v1.1 Group B1: ADX magnitude bands using engine-native _ths_band
# vocabulary at cutoffs aligned with the engine's state-classifier (20, 25)
# and THS_Dir_Momentum saturation (33, 40). See Audit #3 in design lock.
_MACRO_ADX_THRESHOLDS = {
    "critical_below":   15,
    "weak_below":       20,
    "caution_below":    25,
    "acceptable_below": 33,
    "healthy_below":    40,
    "strong_at_or_above": 40,
}


def _macro_adx_condition(adx_value):
    """WKC-001 v1.1 Group B1: weekly ADX magnitude band on macro frame.

    Returns ({label, desc}, thresholds_dict) tuple. Returns (None, None)
    on None input. Uses _ths_band vocabulary to avoid collision with
    engine_state classifier vocabulary (MID-RANGE/RESOLVING/TRENDING).
    """
    if adx_value is None:
        return (None, _MACRO_ADX_THRESHOLDS)
    if adx_value < 15:
        return ({"label": "CRITICAL",
                 "desc": "Weekly ADX below 15 -- no meaningful directional structure on macro frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 20:
        return ({"label": "WEAK",
                 "desc": "Weekly ADX 15-20 -- sub-threshold; no directional regime on macro frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 25:
        return ({"label": "CAUTION",
                 "desc": "Weekly ADX 20-25 -- directional regime just emerging on macro frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 33:
        return ({"label": "ACCEPTABLE",
                 "desc": "Weekly ADX 25-33 -- directional regime confirmed on macro frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 40:
        return ({"label": "HEALTHY",
                 "desc": "Weekly ADX 33-40 -- strong directional regime on macro frame"},
                _MACRO_ADX_THRESHOLDS)
    return ({"label": "STRONG",
             "desc": "Weekly ADX >= 40 -- powerful directional regime on macro frame (THS_Dir_Momentum saturation point)"},
            _MACRO_ADX_THRESHOLDS)


# ============================================================================
# [HFI-001-A] Higher-Frame Interpretation -- primary-frame ADX banding.
# Adds the same _ths_band vocabulary (CRITICAL/WEAK/CAUTION/ACCEPTABLE/HEALTHY/
# STRONG) and identical cutoffs (15/20/25/33/40) to trend_state.directional.adx.
# Closes gap log §A2 Gap 2.
#
# Vocabulary and cutoffs are intentionally identical to _macro_adx_condition
# (locked in WKC-001 v1.1, see HFI-001 design brief §3 D-spec). The constant
# _MACRO_ADX_THRESHOLDS is reused directly -- a sibling _PRIMARY_* alias
# would be visual sugar only. TestHFI001AVocabularyConsistency enforces
# parity at emission level so any drift surfaces immediately.
#
# What changes between the two: the desc text uses the actual primary
# timeframe label (Hourly / Daily / Weekly) and says "primary frame"
# instead of "macro frame".
# ============================================================================
def _primary_adx_condition(adx_value, primary_tf_label):
    """HFI-001-A: classify primary-frame ADX using the same vocabulary as
    macro_frame.adx (WKC-001 v1.1).

    Args:
        adx_value: float ADX reading on the primary frame, or None.
        primary_tf_label: timeframe word for the desc text. Expected values:
            "Hourly" (Profile A), "Daily" (Profile B), "Weekly" (Profile C).
            Falls back to "Primary" if an unexpected value is supplied so
            downstream emission never breaks on Data_Basis drift.

    Returns:
        ({label, desc}, thresholds_dict) tuple. Returns
        (None, _MACRO_ADX_THRESHOLDS) on None input, matching the FPC-001
        convention of always emitting the thresholds dict for schema stability.
    """
    # Defensive: handle unexpected timeframe labels without crashing emission.
    _tf = primary_tf_label if primary_tf_label in ("Hourly", "Daily", "Weekly") else "Primary"
    if adx_value is None:
        return (None, _MACRO_ADX_THRESHOLDS)
    if adx_value < 15:
        return ({"label": "CRITICAL",
                 "desc": f"{_tf} ADX below 15 -- no meaningful directional structure on primary frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 20:
        return ({"label": "WEAK",
                 "desc": f"{_tf} ADX 15-20 -- sub-threshold; no directional regime on primary frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 25:
        return ({"label": "CAUTION",
                 "desc": f"{_tf} ADX 20-25 -- directional regime just emerging on primary frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 33:
        return ({"label": "ACCEPTABLE",
                 "desc": f"{_tf} ADX 25-33 -- directional regime confirmed on primary frame"},
                _MACRO_ADX_THRESHOLDS)
    if adx_value < 40:
        return ({"label": "HEALTHY",
                 "desc": f"{_tf} ADX 33-40 -- strong directional regime on primary frame"},
                _MACRO_ADX_THRESHOLDS)
    return ({"label": "STRONG",
             "desc": f"{_tf} ADX >= 40 -- powerful directional regime on primary frame (THS_Dir_Momentum saturation point)"},
            _MACRO_ADX_THRESHOLDS)


# WKC-001 v1.1 Group B2: secular elevation bands keyed on % above weekly SMA 200.
# Vocabulary is SECULAR_*_ELEVATION (purely positional, distinct from
# extension_analysis vocabulary which is swing-trade-oriented).
_MACRO_ELEVATION_THRESHOLDS = {
    "below_secular_at": 0,
    "early_at":         25,
    "established_at":   75,
    "mature_at":        150,
    "late_at":          300,
}


def _macro_secular_elevation(pct_above_sma200):
    """WKC-001 v1.1 Group B2: weekly SMA 200 elevation band on macro frame.

    Returns ({label, desc}, thresholds_dict) tuple. Returns (None, None)
    on None input. Vocabulary scoped to weekly secular timeframe only;
    do not reuse on daily/monthly without redefinition.
    """
    if pct_above_sma200 is None:
        return (None, _MACRO_ELEVATION_THRESHOLDS)
    if pct_above_sma200 < 0:
        return ({"label": "BELOW_SECULAR_MEAN",
                 "desc": "Price below weekly SMA 200 -- Stage 4 territory or deep secular drawdown"},
                _MACRO_ELEVATION_THRESHOLDS)
    if pct_above_sma200 < 25:
        return ({"label": "EARLY_SECULAR_ELEVATION",
                 "desc": "Within 25% of secular mean -- early phase of secular uptrend"},
                _MACRO_ELEVATION_THRESHOLDS)
    if pct_above_sma200 < 75:
        return ({"label": "ESTABLISHED_SECULAR_ELEVATION",
                 "desc": "Comfortably above secular mean -- secular uptrend in progress"},
                _MACRO_ELEVATION_THRESHOLDS)
    if pct_above_sma200 < 150:
        return ({"label": "MATURE_SECULAR_ELEVATION",
                 "desc": "Significantly above secular mean -- well-developed secular uptrend"},
                _MACRO_ELEVATION_THRESHOLDS)
    if pct_above_sma200 < 300:
        return ({"label": "LATE_SECULAR_ELEVATION",
                 "desc": "Far above secular mean -- late-stage secular advance"},
                _MACRO_ELEVATION_THRESHOLDS)
    return ({"label": "PARABOLIC_SECULAR_ELEVATION",
             "desc": "Multiple-x the secular mean -- rare territory, structural exhaustion risk"},
            _MACRO_ELEVATION_THRESHOLDS)


# ============================================================================
# [HFI-001-B] Higher-Frame Interpretation -- higher_frame.sma200.price_distance
# elevation banding across all three profiles.
# Closes gap log §A2 Gap 1.
#
# Per HFI-001 design brief D2-D5:
#   - Profile A daily   -> CYCLICAL_* vocabulary (this module, new)
#   - Profile B weekly  -> SECULAR_*  vocabulary (REUSES _macro_secular_elevation
#                          above; do NOT add a sibling -- the weekly SMA 200 is
#                          genuinely secular regardless of profile lens, and
#                          fragmenting vocabulary across profiles is a charter
#                          violation. See D3.)
#   - Profile C monthly -> DECADAL_*  vocabulary (this module, new)
#
# Cutoffs are IDENTICAL across all three timeframes per D5: 0 / 25 / 75 / 150
# / 300 percent. Per-timeframe tuning (β) is deferred to HFI-002 pending
# backtest data; D5 was a deliberate empirical decision, not a default.
#
# Vocabulary hygiene: CYCLICAL / SECULAR / DECADAL produce disjoint label
# sets (18 distinct tokens). No overlap with extension_analysis (OVEREXTENDED),
# volume.summary (SUPPORTED ZONE / CONTESTED ZONE), or FPC-001 (WITHIN_ZONE
# / EDGE_OF_ZONE / BEYOND_ZONE). STRUCTURAL_* was rejected for DECADAL to
# avoid collision with floor_failure.context STRUCTURAL_BREAKDOWN.
# ============================================================================
_HFI_DAILY_CYCLICAL_THRESHOLDS = {
    "below_cyclical_at": 0,
    "early_at":          25,
    "established_at":    75,
    "mature_at":         150,
    "late_at":           300,
}


def _daily_cyclical_elevation(pct_above_sma200):
    """HFI-001-B: Profile A daily higher_frame SMA 200 elevation band.

    Vocabulary scoped to the intermediate cyclical timeframe (multi-month
    advances). Parallel structure to _macro_secular_elevation but explicitly
    distinct so the operator never conflates a cyclical band with a secular
    one. See HFI-001 brief D2 for the rationale.

    Returns ({label, desc}, thresholds_dict) tuple. Returns
    (None, _HFI_DAILY_CYCLICAL_THRESHOLDS) on None input, matching the
    FPC-001 convention of always emitting the thresholds dict for schema
    stability.
    """
    if pct_above_sma200 is None:
        return (None, _HFI_DAILY_CYCLICAL_THRESHOLDS)
    if pct_above_sma200 < 0:
        return ({"label": "BELOW_CYCLICAL_MEAN",
                 "desc": "Price below intermediate cyclical mean -- below daily SMA 200"},
                _HFI_DAILY_CYCLICAL_THRESHOLDS)
    if pct_above_sma200 < 25:
        return ({"label": "EARLY_CYCLICAL_ELEVATION",
                 "desc": "Within 25% of intermediate cyclical mean -- early phase of cyclical uptrend on daily SMA 200"},
                _HFI_DAILY_CYCLICAL_THRESHOLDS)
    if pct_above_sma200 < 75:
        return ({"label": "ESTABLISHED_CYCLICAL_ELEVATION",
                 "desc": "Comfortably above intermediate cyclical mean -- cyclical uptrend in progress on daily SMA 200"},
                _HFI_DAILY_CYCLICAL_THRESHOLDS)
    if pct_above_sma200 < 150:
        return ({"label": "MATURE_CYCLICAL_ELEVATION",
                 "desc": "Significantly above intermediate cyclical mean -- well-developed cyclical uptrend on daily SMA 200"},
                _HFI_DAILY_CYCLICAL_THRESHOLDS)
    if pct_above_sma200 < 300:
        return ({"label": "LATE_CYCLICAL_ELEVATION",
                 "desc": "Far above intermediate cyclical mean -- late-stage cyclical advance on daily SMA 200"},
                _HFI_DAILY_CYCLICAL_THRESHOLDS)
    return ({"label": "PARABOLIC_CYCLICAL_ELEVATION",
             "desc": "Multiple-x the intermediate cyclical mean -- rare territory, cyclical exhaustion risk on daily SMA 200"},
            _HFI_DAILY_CYCLICAL_THRESHOLDS)


_HFI_MONTHLY_DECADAL_THRESHOLDS = {
    "below_decadal_at": 0,
    "early_at":         25,
    "established_at":   75,
    "mature_at":        150,
    "late_at":          300,
}


def _monthly_decadal_elevation(pct_above_sma200):
    """HFI-001-B: Profile C monthly higher_frame SMA 200 elevation band.

    Vocabulary scoped to the multi-decade structural timeframe (200 monthly
    bars ~= 17 years of history; the deepest structural lens the engine
    emits). DECADAL_* was chosen over the rejected STRUCTURAL_* prefix to
    avoid collision with floor_failure.context STRUCTURAL_BREAKDOWN. See
    HFI-001 brief D4.

    Returns ({label, desc}, thresholds_dict) tuple. Returns
    (None, _HFI_MONTHLY_DECADAL_THRESHOLDS) on None input.

    Live-validation note (per brief §4 PCM-001 caveat): most tickers'
    Profile C higher_frame is null due to monthly SMA 200 history
    requirement, so live exercise of this helper requires a megacap with
    17+ years of monthly bars (AAPL / MSFT class) or a synthetic fixture.
    """
    if pct_above_sma200 is None:
        return (None, _HFI_MONTHLY_DECADAL_THRESHOLDS)
    if pct_above_sma200 < 0:
        return ({"label": "BELOW_DECADAL_MEAN",
                 "desc": "Price below multi-decade structural mean -- below monthly SMA 200"},
                _HFI_MONTHLY_DECADAL_THRESHOLDS)
    if pct_above_sma200 < 25:
        return ({"label": "EARLY_DECADAL_ELEVATION",
                 "desc": "Within 25% of multi-decade structural mean -- early phase of structural advance on monthly SMA 200"},
                _HFI_MONTHLY_DECADAL_THRESHOLDS)
    if pct_above_sma200 < 75:
        return ({"label": "ESTABLISHED_DECADAL_ELEVATION",
                 "desc": "Comfortably above multi-decade structural mean -- structural advance in progress on monthly SMA 200"},
                _HFI_MONTHLY_DECADAL_THRESHOLDS)
    if pct_above_sma200 < 150:
        return ({"label": "MATURE_DECADAL_ELEVATION",
                 "desc": "Significantly above multi-decade structural mean -- well-developed structural advance on monthly SMA 200"},
                _HFI_MONTHLY_DECADAL_THRESHOLDS)
    if pct_above_sma200 < 300:
        return ({"label": "LATE_DECADAL_ELEVATION",
                 "desc": "Far above multi-decade structural mean -- late-stage structural advance on monthly SMA 200"},
                _HFI_MONTHLY_DECADAL_THRESHOLDS)
    return ({"label": "PARABOLIC_DECADAL_ELEVATION",
             "desc": "Multiple-x the multi-decade structural mean -- rare territory, generational exhaustion risk on monthly SMA 200"},
            _HFI_MONTHLY_DECADAL_THRESHOLDS)


# WKC-001 v1.1 Group C: stage classification descriptions.
def _macro_stage_desc(stage_label):
    """Returns phase-specific desc for a Weinstein stage label."""
    return {
        "STAGE_1_BASING":     "Basing/accumulation phase -- bearish structure but momentum stabilizing/turning up",
        "STAGE_2_ADVANCING":  "Markup phase -- bullish structure aligned with positive momentum",
        "STAGE_3_TOPPING":    "Topping/distribution phase -- bullish structure but momentum rolling over",
        "STAGE_4_DECLINING":  "Markdown phase -- bearish structure aligned with negative momentum",
    }.get(stage_label, "Stage classification unavailable")


# ============================================================================
# [SBC-001] Swing Breakout Confirmation -- breakout_rvol banding.
# Reuses the existing volume.rvol band vocabulary (output.py:2225-2237) for
# engine-wide coherence: QUIET / BELOW AVERAGE / NORMAL / ELEVATED / HIGH /
# EXTREME at cutoffs 0.5 / 0.8 / 1.2 / 2.0 / 3.0.
#
# Closes gap log §A2 Gap 4: breakout_rvol was raw value only, lacking the
# qualifier that the current-bar volume.rvol already had. The breakout-bar
# RVOL is arguably more analytically important (institutional commitment on
# the breakout itself), so banding it brings symmetry to the engine.
# ============================================================================
_BREAKOUT_RVOL_THRESHOLDS = {
    "quiet_below":         0.5,
    "below_average_below": 0.8,
    "normal_below":        1.2,
    "elevated_below":      2.0,
    "high_below":          3.0,
    "extreme_at_or_above": 3.0,
}


def _breakout_rvol_band(rvol_value):
    """SBC-001: classify breakout-bar RVOL using the same band vocabulary
    as the current-bar volume.rvol classifier in output.py.

    Returns ({label, desc}, thresholds_dict) tuple. Returns (None, thresholds)
    on None input.
    """
    if rvol_value is None:
        return (None, _BREAKOUT_RVOL_THRESHOLDS)
    if rvol_value < 0.5:
        return ({"label": "QUIET",
                 "desc": "Breakout bar volume well below 20-bar average -- insufficient institutional commitment on the breakout"},
                _BREAKOUT_RVOL_THRESHOLDS)
    if rvol_value < 0.8:
        return ({"label": "BELOW AVERAGE",
                 "desc": "Breakout bar volume below 20-bar average -- weak conviction; breakout quality compromised"},
                _BREAKOUT_RVOL_THRESHOLDS)
    if rvol_value < 1.2:
        return ({"label": "NORMAL",
                 "desc": "Breakout bar volume near 20-bar average -- routine participation; no above-average institutional commitment"},
                _BREAKOUT_RVOL_THRESHOLDS)
    if rvol_value < 2.0:
        return ({"label": "ELEVATED",
                 "desc": "Breakout bar volume 1.2-2.0x 20-bar average -- above-average institutional commitment on the breakout"},
                _BREAKOUT_RVOL_THRESHOLDS)
    if rvol_value < 3.0:
        return ({"label": "HIGH",
                 "desc": "Breakout bar volume 2.0-3.0x 20-bar average -- strong institutional commitment on the breakout"},
                _BREAKOUT_RVOL_THRESHOLDS)
    return ({"label": "EXTREME",
             "desc": "Breakout bar volume >= 3.0x 20-bar average -- exceptional institutional commitment; high-conviction breakout"},
            _BREAKOUT_RVOL_THRESHOLDS)


# ============================================================================
# [FPC-001] Profile C floor_proximity_pct banding.
# Banding aligns with the Profile C floor proximity gate at
# gates.py:_gate_floor_proximity_c (gate strict-rejects when x > 15.0%).
#
# Closes gap log §A2 Gap 3. The floor_proximity_pct field was emitted as a
# raw value/unit/desc only -- with no qualifier telling the operator whether
# they were inside the entry zone, at the edge, or deep in rejection territory.
# This bundle adds the condition + thresholds pair (same pattern as
# WKC-001 v1.1 macro_frame.adx.condition and SBC-001 breakout_rvol.condition).
#
# Boundary semantics:
#   - EDGE_OF_ZONE upper bound is inclusive at 15.0 to match the gate
#     (gate uses `> 15.0` strict, so x == 15.0 still passes the gate).
#   - All other internal boundaries use strict `<` per engine RVOL-band
#     convention (output.py:2225-2237).
# ============================================================================
_FLOOR_PROXIMITY_PCT_THRESHOLDS = {
    "within_zone_below":            5.0,
    "edge_of_zone_at_or_below":     15.0,  # gate boundary -- inclusive
    "beyond_zone_below":            30.0,
    "far_beyond_zone_below":        100.0,
    "extreme_distance_at_or_above": 100.0,
}


def _floor_proximity_pct_band(pct_value):
    """FPC-001: classify Profile C floor_proximity_pct using bands aligned
    with the Profile C 15% gate threshold.

    Returns ({label, desc}, thresholds_dict) tuple. Returns (None, thresholds)
    on None input.

    The 15.0% boundary is gate-critical and boundary-inclusive (matching
    gates.py:_gate_floor_proximity_c which uses `> 15.0` strict comparison).
    """
    if pct_value is None:
        return (None, _FLOOR_PROXIMITY_PCT_THRESHOLDS)
    if pct_value < 5.0:
        return ({"label": "WITHIN_ZONE",
                 "desc": "Price within 5% of secular floor (SMA 200) -- tightly floor-anchored entry zone"},
                _FLOOR_PROXIMITY_PCT_THRESHOLDS)
    if pct_value <= 15.0:
        return ({"label": "EDGE_OF_ZONE",
                 "desc": "Price 5-15% from secular floor -- approaching the 15% entry gate limit; floor proximity audit still passes"},
                _FLOOR_PROXIMITY_PCT_THRESHOLDS)
    if pct_value < 30.0:
        return ({"label": "BEYOND_ZONE",
                 "desc": "Price 15-30% from secular floor -- beyond the 15% entry gate; floor proximity audit fails"},
                _FLOOR_PROXIMITY_PCT_THRESHOLDS)
    if pct_value < 100.0:
        return ({"label": "FAR_BEYOND_ZONE",
                 "desc": "Price 30-100% from secular floor -- significantly stretched from secular reference"},
                _FLOOR_PROXIMITY_PCT_THRESHOLDS)
    return ({"label": "EXTREME_DISTANCE",
             "desc": "Price more than 100% above secular floor -- extreme distance from SMA 200; deeply extended secular regime"},
            _FLOOR_PROXIMITY_PCT_THRESHOLDS)


# [WKC-002] Higher-frame stage classification helpers.
# Same stage labels as macro_frame (timeframe-agnostic per Design Lock §A3);
# desc text adapted per timeframe to acknowledge cyclical-vs-secular semantics.
def _hf_framework_desc():
    """Shared framework_desc string for any timeframe."""
    return ("STAGE_1: Basing/Accumulation | "
            "STAGE_2: Advancing/Markup | "
            "STAGE_3: Topping/Distribution | "
            "STAGE_4: Declining/Markdown")


def _hf_purpose_desc(timeframe_label):
    """Timeframe-aware framework purpose desc for higher_frame.market_stage.

    Daily   = intermediate cyclical regime (months to ~1 year)
    Weekly  = secular regime (~1-4 years; same scale as Profile A macro_frame)
    Monthly = deeply secular regime (multi-cyclical, generational)
    """
    if timeframe_label == "DAILY":
        return ("Intermediate cyclical classification -- identifies which phase "
                "of the multi-month advance/decline this stock currently occupies "
                "on the daily timeframe. Combine with macro_frame.market_stage to "
                "detect multi-timeframe confluence (full alignment) or divergence "
                "(cyclical and secular trends disagreeing).")
    if timeframe_label == "WEEKLY":
        return ("Secular structural classification -- identifies which phase of "
                "the multi-year advance/decline this stock currently occupies on "
                "the weekly timeframe. Used to filter for ideal long-side entry "
                "candidates (Stage 2), avoid structural traps (Stage 3 topping, "
                "Stage 4 declining), and recognize early-stage opportunities (Stage 1 basing).")
    if timeframe_label == "MONTHLY":
        return ("Deeply secular structural classification -- identifies which "
                "phase of the multi-year-to-generational advance/decline this "
                "stock currently occupies on the monthly timeframe. Operates at "
                "a longer scale than weekly Weinstein analysis; captures secular "
                "regime shifts that span multiple cyclical cycles.")
    return "Stage classification framework unavailable"


def _hf_stage_desc(stage_label, timeframe_label):
    """Timeframe-aware phase desc. Falls through to generic _macro_stage_desc
    when timeframe is weekly (same semantics as Profile A macro_frame).
    For daily/monthly, descriptions acknowledge the different cyclical scale.
    """
    if timeframe_label == "WEEKLY":
        return _macro_stage_desc(stage_label)
    # Daily and monthly use the same structural language; timeframe context
    # comes from the enclosing higher_frame.timeframe.label field.
    return _macro_stage_desc(stage_label)


# ===== TRADE_SETUP (SETUP-001: custom assembly, 5 sub-groups) =====

_TS_TARGETS = []
_TS_STOPS = []
_TS_ENTRY_ZONE = []
_TS_RALLY = []
_TS_EXEC_WINDOW = []

_TRADE_SETUP_SUBGROUPS = [
    ("target",           _TS_TARGETS),
    ("stop",             _TS_STOPS),
    ("entry_zone",       _TS_ENTRY_ZONE),
    ("rally",            _TS_RALLY),
    ("execution_window", _TS_EXEC_WINDOW),
]

# SETUP-001: All sub-groups custom-assembled, 0 tuple-mapped keys
_SETUP_TOTAL = sum(len(t) for _, t in _TRADE_SETUP_SUBGROUPS)
assert _SETUP_TOTAL == 0


# ===== EXTENSION_ANALYSIS (EXT-001: new top-level section, custom assembly) =====

_GROUP_EXTENSION_ANALYSIS = []


# ===== PSYCHOLOGICAL_LEVELS (PSY-002: new top-level section, custom assembly) =====

_GROUP_PSYCHOLOGICAL_LEVELS = []


# ===== ENTRY_PROXIMITY (custom assembly in _transform_output -- PROX-001) =====

_GROUP_ENTRY_PROXIMITY = []


# ===== EXIT_SIGNALS (custom assembly in _transform_output -- EXIT-001) =====

_GROUP_EXIT_SIGNALS = []


# ===== _DEBUG (28 keys — flat, optional) =====

_GROUP_DEBUG = [
    ("actual_price",     "actual_price"),
    ("adx_t",            "adx_t"),
    ("adx_t1",           "adx_t1"),
    ("adx_t2",           "adx_t2"),
    ("adx_accel",        "adx_accel"),
    ("adx_accel_state",  "adx_accel_state"),
    ("di_plus",          "di_plus"),
    ("di_minus",         "di_minus"),
    ("atr_raw",          "atr_raw"),
    ("hard_stop_raw",    "hard_stop_raw"),
    ("resistance_raw",   "resistance_raw"),
    ("structural_floor_raw", "structural_floor_raw"),
    ("price_scaler",     "price_scaler"),
    ("is_etf",           "is_etf_internal"),
    ("_is_lse_etf",      "is_lse_etf"),
    ("_ssg_adjusted",    "ssg_adjusted"),
    ("_ssg_original_raw","ssg_original_raw"),
    ("_ssg_reason",      "ssg_reason"),
    ("_early_return",    "early_return"),
    ("ma_squeeze",       "ma_squeeze"),
    ("clean_ticker",     "clean_ticker"),
    ("currency",         "currency"),
    ("bars_per_day",     "bars_per_day"),
    ("window_count",     "window_count"),
    ("adx_col",          "adx_col"),
    ("dmp_col",          "dmp_col"),
    ("dmn_col",          "dmn_col"),
    ("vwap_col",         "vwap_col"),
]
assert len(_GROUP_DEBUG) == 28


# ---------------------------------------------------------------------------
# SEM-001 Renames — for reference
# ---------------------------------------------------------------------------

_SEM001_RENAMES = {
    "Inst_Churn":           "churn",
    "Cons_High":            "high",
    "Stop_Adjusted_Flag":   "adjusted",
    "RN_Target_Proximity":  "target",
    "RN_Stop_Proximity":    "stop",
    "RN_Floor_Proximity":   "floor",
    "ATR_Dist":             "atr_distance",
    "ATR_Dist_Anchor":      "atr_distance_anchor",
    "ATR_Dist_Note":        "atr_distance_note",
    "Floor_Prox_Pct":       "floor_proximity_pct",
    "Floor_Failure_Reclaim":"reclaim_progress",
}


# ---------------------------------------------------------------------------
# Build the complete set of mapped flat keys (for coverage audit)
# ---------------------------------------------------------------------------

def _all_mapped_flat_keys():
    keys = set()
    for fk, _ in _GROUP_TRADE_SNAPSHOT_MAPPED:
        keys.add(fk)
    for fk, _ in _GROUP_TRADE_SNAPSHOT_CLASSIFICATION:
        keys.add(fk)
    # entry_strategy sub-object sources (injected, not in a mapping table)
    keys.add("Entry_Reference")
    # PE-42: new flat metric keys consumed by transform
    keys.update(["Live_Price", "Bar_Close_Price", "Price_Source",
                 "Data_Basis", "Snapshot_Time", "Bar_Range", "_tz_label"])
    for _, table in _TRADE_QUALITY_SUBGROUPS:
        for fk, _ in table:
            keys.add(fk)
    for fk, _ in _TQ_SCALARS:
        keys.add(fk)
    for fk, _ in _GROUP_TRADE_RISK:
        keys.add(fk)
    for _, table in _TREND_STATE_SUBGROUPS:
        for fk, _ in table:
            keys.add(fk)
    for fk, _ in _GROUP_PRICE_INDICATORS:
        keys.add(fk)
    for fk, _ in _GROUP_FLOOR_ANALYSIS_TOP:
        keys.add(fk)
    for fk, _ in _HIGHER_FRAME_MAP:
        keys.add(fk)
    # [WKC-001] Register Context_Macro_* flat keys for MAPPED_FLAT_KEYS membership.
    for fk, _ in _MACRO_FRAME_MAP:
        keys.add(fk)
    for _, table in _TRADE_SETUP_SUBGROUPS:
        for fk, _ in table:
            keys.add(fk)
    for fk, _ in _GROUP_ENTRY_PROXIMITY:
        keys.add(fk)
    for fk, _ in _GROUP_EXIT_SIGNALS:
        keys.add(fk)
    for fk, _ in _GROUP_DEBUG:
        keys.add(fk)

    # SelfDoc Batch 1: Keys from custom-assembled sections (no longer in tuple tables)
    # THS-002: trend_health keys
    keys.update([
        "Trend_Health_Score", "THS_Label", "THS_Floor_Buffer", "THS_Dir_Momentum",
        "THS_Trend_Age", "THS_Structure", "THS_Floor_Buffer_Label",
        "THS_Dir_Momentum_Label", "THS_Trend_Age_Label", "THS_Structure_Label",
        # STRUCT-001-TFR-1: Phase 3 advisory keys
        "THS_Death_Cross_Cap", "THS_Component_Cap", "THS_VWAP_Floor_Penalty",
        "THS_VWAP_Floor_Note", "THS_Context_Advisory",
    ])
    # TS-001: trend_state keys
    keys.update([
        "Engine_State", "Engine_State_Desc", "Trend_Age_Bars", "Trend_Age_Max",
        "Active_Modifiers", "Active_Modifiers_List", "Inst_Churn",
        "ADX", "ADX_Accel", "ADX_Accel_State", "DI_Plus", "DI_Minus",
        "DI_Spread", "DI_Bias",
    ])
    # EXIT-001: exit_signals keys
    keys.update([
        "Exit_Signal", "Exit_Triggers", "Exit_Reason",
        "Exit_VWAP_Counter", "Exit_EMA21_Counter", "Exit_EMA8_Counter", "Established_Hourly_Low",
    ])
    # PROX-001: entry_proximity keys
    keys.update([
        "Proximity_Signal", "Proximity_Blocking_Gate", "Proximity_Distance",
        "Proximity_Target", "Proximity_Note", "Proximity_Condition_Label",
        "Proximity_Condition_Desc", "Proximity_Distance_Unit",
    ])
    # RISK-001: trade_risk keys
    keys.update([
        "Reward_Risk", "Reward_Risk_Note", "Capital_Reward_Risk",
        "Capital_RR_Label", "Risk_Per_Unit", "Expectancy_Threshold",
        "Expectancy_Threshold_Note", "Risk_Summary_Label", "Risk_Summary_Desc",
        # RISK-UX-001: Blue_Sky + Fundamental keys (relocated/restructured)
        "Blue_Sky_Detected", "Blue_Sky_Target", "Blue_Sky_Method", "Blue_Sky_ATR_Headroom",
        "Fundamental_RR", "Fundamental_RR_Label", "Fundamental_Target",
        "Fundamental_Floor", "Fundamental_Target_High", "Fundamental_Analyst_Count",
        "Fundamental_RR_Note",
    ])

    # SelfDoc Batch 2: Keys from custom-assembled sections
    # VOL-003: volume keys
    keys.update([
        "Vol_Confirm_Ratio", "Vol_Confirm_State", "Vol_Confirm_Bias",
        "Vol_PoC_Price", "Vol_PoC_Distance_ATR", "Vol_PoC_Position",
        "AVWAP_Price", "AVWAP_Position", "AVWAP_Distance_ATR",
        "AVWAP_Bias", "AVWAP_Bias_Desc", "PoC_Bias", "PoC_Bias_Desc",
        "Volume_Context_Label", "Vol_Histogram_Period",
        "RVOL_Value", "RVOL_Label",
        "Vol_Summary_Label", "Vol_Summary_Bias", "Vol_Summary_Confidence", "Vol_Summary_Detail",
        "ADV_20_Dollar",
    ])
    # VTRIG-001: volume_confirmation flat keys
    keys.update([
        "Vol_Confirm_Tier", "Vol_Confirm_Multiplier",
        "Vol_Confirm_15m", "Vol_Confirm_30m", "Vol_Confirm_60m",
    ])
    # VOL-004: volume display enhancement flat keys
    keys.update([
        "Bar_Volume", "Session_Volume",
    ])
    # SBO-001 Phase 2: swing_breakout_confirmation flat keys
    keys.update([
        "SBO_Breakout_Bar_Age", "SBO_Trending_Reached",
        "SBO_Confirmation_Timeout", "SBO_RVOL",
    ])
    # BRK-001-GAP-2: Breakout thesis invalidation flat keys
    # Note: BRK_Thesis_Note is registered here (not in the prompt's list)
    # to keep the audit symmetric with other *_Note siblings; without it
    # every thesis-failure run surfaces BRK_Thesis_Note as unmapped.
    keys.update([
        "Breakout_Thesis_Status",
        "BRK_Thesis_New_Support", "BRK_Thesis_Bar_Close", "BRK_Thesis_Delta",
        "BRK_Thesis_Note",
    ])
    # FA-001: floor_analysis keys
    keys.update([
        "Floor_Failure_Context", "Floor_Breach_Dist", "Floor_Failure_Reclaim",
        "Floor_Failure_Threshold", "Anchor_Label", "Anchor_Type", "Floor_Anchor_Type",
        "Floor_Anchor_Label", "Extension_Anchor_Type", "Extension_Anchor_Label",
        "Floor_Failure_Status_Label", "Floor_Failure_Status_Desc",
        "Floor_Prox_Pct",
        "Context_EMA_8", "Context_EMA_21", "Context_EMA_Stacked",
        "Context_EMA_Bias", "Context_EMA_Bias_Desc", "Context_SMA50_Slope_Bias",
        # [EMA50-001] Canonical aggregated EMA 50 keys per DQ-10 -- these
        # have no SMA 50 counterpart (SMA 50 pattern produces only
        # Context_SMA50_Slope_Bias, not canonical price or slope).
        "Context_EMA_50", "Context_EMA_50_Slope", "Context_EMA_50_Slope_Bias",
    ])
    # SNAP-001: trade_snapshot keys (price_indicators absorbed)
    keys.update([
        "Price", "Structural_Floor", "Resistance", "ADV_20",
        "EMA_8", "EMA_21", "SMA_50", "SMA_200", "VWAP", "ATR",
        "Convexity_Class", "ETF_Primary_Exchange", "ETF_Detection_Source", "Is_ETF",
        # BUG-R1: inversion note
        "Support_Resistance_Note",
    ])
    # SETUP-001: trade_setup keys
    keys.update([
        "Profit_Target", "Profit_Target_Source", "Profit_Target_Role",
        "Profit_Target_Synthetic", "Profit_Target_Synthetic_Note",
        "Hard_Stop", "Hard_Stop_Note", "Original_Hard_Stop",
        "Stop_Adjusted_Flag", "Stop_Adjusted_Reason",
        "Stop_Proximity_Blocked", "Stop_Gap_ATR",
        "Pullback_Zone_Upper", "Cons_High", "Resistance_Note",
        "Fib_382_Level", "Fib_500_Level", "Fib_Confluence",
        "Fib_A_382_Level", "Fib_A_500_Level", "Fib_A_Confluence",
        "MM_Target", "MM_Rally_ATR",
        # [ENG-006] Fibonacci extension projection levels (display-scaled)
        "Fib_Ext_1272_Level", "Fib_Ext_1618_Level", "Fib_Ext_2618_Level",
        "Window_Limit", "Window_Reset_Event", "window_count",
    ])
    # EXT-001: extension_analysis keys
    keys.update([
        "ATR_Dist", "ATR_Dist_Anchor", "ATR_Dist_Note",
        "Extension_Limit", "Trend_Quality_Override",
    ])
    # PA-001 Phase 2: daily protective + extension + RSI + advisory flat keys
    keys.update([
        "Daily_Extension_Distance", "Daily_Extension_Label",
        "Daily_Extension_Caution_Note",
        "Daily_Protective_Anchor", "Daily_ATR", "Daily_Hard_Stop",
        "Daily_RSI", "Daily_RSI_Admissibility", "Daily_RSI_Admissibility_Desc",
        "Capital_RR_Role", "Capital_RR_Role_Desc",
        "Floor_Proximity_Exempted", "Floor_Proximity_Exemption_Desc",
    ])
    # PSY-002: psychological_levels keys
    keys.update([
        "Psych_Floor", "Psych_Ceiling", "Psych_Floor_Dist_Pct",
        "Psych_Floor_Near_Technical", "Psych_Floor_Near_Structural",
        "Psych_Ceiling_Near_Technical", "Psych_Increment", "Psych_Ceiling_Dist_Pct",
        "RN_Target_Proximity", "RN_Stop_Proximity", "RN_Floor_Proximity",
    ])
    # PA-001 Phase 3: hierarchy flat keys (DQ-9, DQ-10)
    keys.update([
        "Target_Hierarchy_Count", "Target_Hierarchy_Winner",
        "Floor_Hierarchy_Count",
    ])
    # PA-001 Phase 4: DQ-11 medium-term overextension flat keys
    keys.update([
        "MediumTerm_Extension_Pct",
        "MediumTerm_Extension_Label",
        "MediumTerm_Extension_Caution_Note",
    ])
    # [PCT-001] Cross-profile percentage-from-anchor flat keys (Profile A
    # native, Profile B alias for MediumTerm_Extension_Pct per DQ-8).
    keys.update([
        "Pct_From_Daily_EMA21",
        "Pct_From_Daily_SMA50",
    ])
    # SFR-001: Signal Freshness flat key
    keys.add("Signal_Freshness")

    # AVWAP-001 Phase 2: VWAP trigger + entry zone flat keys (written by trigger.py)
    keys.update([
        "Pullback_Zone_Lower", "Entry_Zone_Reference", "Entry_Zone_Width_ATR",
        "VWAP_Trigger_Status", "VWAP_Trigger_Price", "VWAP_Trigger_Confirmed",
        "VWAP_Trigger_Note",
    ])

    # AVWAP-001 Phase 3: SFR-001 freshness integration
    keys.add("Signal_Freshness_Note")

    # AVWAP-001 DQ-6: Session VWAP context flat keys
    keys.update([
        "Session_VWAP_Bias", "Session_VWAP_Bias_Desc",
        "Session_VWAP_Distance_ATR",
        "Session_VWAP_Advisory", "Session_VWAP_Advisory_Desc",
    ])

    # AVWAP-001 DQ-4: Extension limit note (Profile A retirement)
    keys.add("Extension_Limit_Note")
    # AVWAP-001: Extension limit effective key
    keys.add("Extension_Limit_Effective")

    # CQS-001: Consolidation Quality Score flat keys
    keys.update([
        "CQS_Composite_Score", "CQS_Composite_Label",
        "CQS_ATR_Gate_Passed", "CQS_ATR_Ratio",
        "CQS_Range_Contraction_Score", "CQS_Volume_Contraction_Score",
        "CQS_VCP_Score", "CQS_VCP_Swing_Lows_Found",
        "CQS_Volume_Terminal_Ratio", "CQS_Caution_Note",
    ])

    # IVR-001: Volatility Regime Context flat keys
    keys.update([
        "IV_Current", "HV_30D", "IV_HV_Ratio",
        "Volatility_Regime", "Volatility_Interpretation",
        "Volatility_Regime_Desc", "Volatility_Interpretation_Desc",
        "Volatility_Caution_Factor",
    ])

    # RLY-001: Rally state primitive flat keys (Spec §3.3)
    keys.update([
        "Rally_Up_Bar_Count_Primary", "Rally_Up_Bar_Count_Context",
        "Rally_Up_Bar_Ratio_Primary", "Rally_Up_Bar_Ratio_Context",
        "Rally_Window_Bars", "Rally_Magnitude_ATR",
        "Rally_Anchor_Price", "Rally_Maturity_Label",
    ])

    # RLC-001: Reclaim Quality Score (Tennis Ball Action) flat key.
    # Backs action_summary.reclaim_quality sub-object (attached in output.py
    # on VALID x RECLAIM verdict only — positive-only design per Spec §2.2).
    keys.add("Reclaim_Quality_Pct")

    # ITS-001: Intraday-Tactical Surface flat keys (Spec §4.6). All 18 keys
    # are None on Profile B/C and on defensive Profile A paths. Backs the
    # top-level intraday_tactical group (assembled via sentinel-key idiom
    # from `_intraday_tactical_block` in flat_metrics per Spec §5.2).
    keys.update([
        "Intraday_Event_Type",
        "Intraday_Event_Bars_Ago",
        "Intraday_Event_Magnitude_Pct",
        "Intraday_Event_Magnitude_ATR",
        "Intraday_Event_RVOL",
        "Intraday_Shelf_Detected",
        "Intraday_Shelf_Upper",
        "Intraday_Shelf_Lower",
        "Intraday_Shelf_Bar_Count",
        "Intraday_Shelf_Tightness_Ratio",
        "Intraday_Shelf_Position",
        "Intraday_Stop_ATR_Volatility",
        "Intraday_Stop_Shelf_Structural",
        "Intraday_Target_Mode",
        "Intraday_Target_Primary",
        "Intraday_Target_Secondary",
        "Intraday_Target_Applicable",
        "Intraday_Lookback_Stale",
        # ITS-001 v1.1: entry_zone flat keys (Spec §4.8 item 1).
        "Intraday_Entry_Zone_Mode",
        "Intraday_Entry_Zone_Applicable",
        "Intraday_Entry_Touchback_Zone_Lower",
        "Intraday_Entry_Touchback_Zone_Upper",
        "Intraday_Entry_Range_Zone_Lower",
        "Intraday_Entry_Range_Zone_Upper",
        "Intraday_Entry_Range_Target_Implied",
        "Intraday_Entry_Breakout_Trigger_Structural",
        "Intraday_Entry_Breakout_Trigger_Confirmed",
    ])

    return keys

MAPPED_FLAT_KEYS = _all_mapped_flat_keys()


# ---------------------------------------------------------------------------
# VOL-004: K/M volume formatting
# ---------------------------------------------------------------------------

def _format_volume(val):
    """VOL-004: Human-readable K/M formatting for volume values.

    Returns formatted string or None if val is None/invalid.
    < 1,000       -> raw integer string ("952")
    1,000-999,999 -> K format ("641K", "1.28K")
    >= 1,000,000  -> M format ("4.28M", "12.5M")
    """
    if val is None:
        return None
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    if val < 0:
        return None
    if val < 1_000:
        return str(int(round(val)))
    elif val < 1_000_000:
        k = val / 1_000
        return f"{k:.1f}K" if k < 100 else f"{int(round(k))}K"
    else:
        m = val / 1_000_000
        return f"{m:.2f}M" if m < 100 else f"{int(round(m))}M"


def _format_dollar_volume(val):
    """VOL-004: K/M formatting with $ prefix for dollar volumes."""
    formatted = _format_volume(val)
    return f"${formatted}" if formatted else None


def _detect_source_tier(source_label_upper: str) -> str | None:
    """Map legacy Profit_Target_Source vocabulary to hierarchy tier label.

    Returns the canonical hierarchy tier label string when the legacy source
    label conceptually corresponds to a known tier. Returns None for fallback
    cases (BRK-001 fallback exhausted, FALLBACK_HOURLY, None) — caller must
    skip re-derive when this returns None.

    Used by DSP-001 / FRR-001-BUG-1 / CEG-002-BUG-1 fix at the post-hierarchy
    re-derive site to determine whether the current source.label already
    conceptually matches the escalation_winner tier (no re-derive needed) or
    differs from it (re-derive needed).

    Vocabulary mapping rationale:
        - "ANALYST" substring   → ANALYST_CONSENSUS (FRR-001 ANALYST_CONSENSUS write)
        - "ATR_PROJECTION" or
          "ATR PROJECTION"      → ATR_PROJECTION (CEG-002 blue-sky / RWD-001 blue-sky)
        - "MEASURED" substring  → MEASURED_MOVE (RWD-001 MM, ENG-004 MM)
        - "WEEKLY" substring    → WEEKLY_HIGH (PE-41 weekly escalation)
        - "PSYCH" substring     → PSYCHOLOGICAL (PSY-001)
        - "RESISTANCE" or
          "10_BAR" substring    → DAILY_HIGH (Profile B technical default + Profile A 10-bar)
        - Anything else         → None (skip re-derive for safety)

    Profile A non-handling rationale (DSP-001-FOLLOWUP-1, S142-cont decision):
        "DAILY_CTX" is the canonical Profile A non-BRK source label. It is
        intentionally unmapped here — returning None falls through to the
        unknown-vocab safety branch in the caller, preserving the label
        verbatim. This preserves Profile A's frame discipline distinct from
        Profile B's hierarchy tier vocabulary; conflating the two via
        re-derive could mask Profile A frame distinctions. Live observed
        2026-05-04 across REL.L A, AAPL A, AVGO A, GOOGL A — all four
        correctly preserved "DAILY_CTX" via the safety branch with zero
        escalation_winner mismatch on the actual hierarchy tiers.
    """
    if not source_label_upper:
        return None
    if "ANALYST" in source_label_upper:
        return "ANALYST_CONSENSUS"
    if "ATR_PROJECTION" in source_label_upper or "ATR PROJECTION" in source_label_upper:
        return "ATR_PROJECTION"
    if "MEASURED" in source_label_upper:
        return "MEASURED_MOVE"
    if "WEEKLY" in source_label_upper:
        return "WEEKLY_HIGH"
    if "PSYCH" in source_label_upper:
        return "PSYCHOLOGICAL"
    if "RESISTANCE" in source_label_upper or "10_BAR" in source_label_upper:
        return "DAILY_HIGH"
    return None


# ---------------------------------------------------------------------------
# RLY-001: rally_state group assembly
# Spec: RLY001_Rally_Age_Streak_Primitive_Spec_v1_0 §3.2, §4.3
# ---------------------------------------------------------------------------

_RLY_FRAME_BY_PROFILE = {
    "A": ("hourly", "daily"),
    "B": ("daily", "weekly"),
    "C": ("weekly", "monthly"),
}

# Mirror of compute.py constants to keep transform.py self-contained for
# the flat→grouped reconstruction (per spec §3.3 + §4.3).
_RLY_WINDOW_BARS = 15
_RLY_MATURE_RATIO_THRESHOLD = 10.0 / 15.0
_RLY_MATURE_MAGNITUDE_ATR_THRESHOLD = 5.0


def _assemble_rally_state_group(flat_metrics):
    """RLY-001: Rebuild the rally_state grouped sub-object from flat keys.

    Per spec §3.2 / §4.3. Returns None when Rally_Maturity_Label is null
    (or any required key is null) — equivalent to the defensive-null path
    in _assemble_rally_state.
    """
    label = flat_metrics.get("Rally_Maturity_Label")
    p_up = flat_metrics.get("Rally_Up_Bar_Count_Primary")
    c_up = flat_metrics.get("Rally_Up_Bar_Count_Context")
    p_ratio = flat_metrics.get("Rally_Up_Bar_Ratio_Primary")
    c_ratio = flat_metrics.get("Rally_Up_Bar_Ratio_Context")
    window_bars = flat_metrics.get("Rally_Window_Bars")
    magnitude = flat_metrics.get("Rally_Magnitude_ATR")
    anchor = flat_metrics.get("Rally_Anchor_Price")

    if label is None or p_up is None or c_up is None or magnitude is None or anchor is None:
        return None

    # Profile detection — mirrors the _floor_anchor_type pattern at the
    # floor_hierarchy assembly site for consistency.
    _floor_anchor_type = flat_metrics.get("Floor_Anchor_Type", "")
    if _floor_anchor_type in ("VWAP", "EMA_21"):
        _p_code = "A"
    elif _floor_anchor_type == "SMA_50":
        _p_code = "B"
    elif _floor_anchor_type == "SMA_200":
        _p_code = "C"
    else:
        _p_code = "A"
    p_frame, c_frame = _RLY_FRAME_BY_PROFILE.get(_p_code, ("", ""))

    # current_price + atr_value reconstruction.
    current_price = flat_metrics.get("Price")
    if current_price is None:
        current_price = anchor  # degenerate fallback
    try:
        if magnitude not in (0, 0.0):
            atr_value = (float(current_price) - float(anchor)) / float(magnitude)
        else:
            atr_value = None
    except (TypeError, ZeroDivisionError):
        atr_value = None

    ratio_threshold = _RLY_MATURE_RATIO_THRESHOLD
    mag_threshold = _RLY_MATURE_MAGNITUDE_ATR_THRESHOLD
    ratio_met = c_ratio is not None and c_ratio >= ratio_threshold
    mag_met = magnitude >= mag_threshold
    both_met = ratio_met and mag_met

    if label == "RALLY_MATURE":
        maturity_desc = (
            f"RALLY_MATURE -- context up-bar ratio {c_ratio:.2f} >= 10/15 "
            f"AND magnitude {magnitude:.2f} ATR >= 5.0"
        )
    else:
        _unmet_parts = []
        if not ratio_met:
            _unmet_parts.append(f"context ratio {c_ratio:.2f} < 10/15")
        if not mag_met:
            _unmet_parts.append(f"magnitude {magnitude:.2f} ATR < 5.0")
        maturity_desc = "NORMAL -- " + " and ".join(_unmet_parts) if _unmet_parts else "NORMAL"

    _wb = window_bars if window_bars is not None else _RLY_WINDOW_BARS

    return {
        "primary": {
            "up_bar_count": p_up,
            "window_bars": _wb,
            "ratio": round(p_ratio, 2) if p_ratio is not None else None,
            "frame": p_frame,
            "desc": (
                f"{p_up} of last {_wb} {p_frame} bars closed above prior close "
                f"(ratio {p_ratio:.2f})"
            ) if p_ratio is not None else None,
        },
        "context": {
            "up_bar_count": c_up,
            "window_bars": _wb,
            "ratio": round(c_ratio, 2) if c_ratio is not None else None,
            "frame": c_frame,
            "desc": (
                f"{c_up} of last {_wb} {c_frame} bars closed above prior close "
                f"(ratio {c_ratio:.2f})"
            ) if c_ratio is not None else None,
        },
        "magnitude": {
            "atr_widths": round(magnitude, 2),
            "anchor_price": round(float(anchor), 2),
            "current_price": round(float(current_price), 2),
            "atr_value": round(atr_value, 2) if atr_value is not None else None,
            "desc": (
                f"Rally has spanned {magnitude:.2f} ATR widths from "
                f"window-start anchor at ${float(anchor):.2f}"
            ),
        },
        "maturity": {
            "label": label,
            "trigger": {
                "context_ratio_threshold": round(ratio_threshold, 3),
                "context_ratio_actual": round(c_ratio, 2) if c_ratio is not None else None,
                "context_ratio_met": ratio_met,
                "magnitude_atr_threshold": mag_threshold,
                "magnitude_atr_actual": round(magnitude, 2),
                "magnitude_atr_met": mag_met,
                "both_met": both_met,
            },
            "desc": maturity_desc,
        },
    }


# ---------------------------------------------------------------------------
# _transform_output
# ---------------------------------------------------------------------------

def _transform_output(action_summary: dict, flat_metrics: dict,
                      debug: bool = False) -> dict:
    """Transform action_summary + flat metrics into concept-grouped dict.

    DIAG-001 Phase 2B: Signature changed from (status, diagnostic, flat_metrics)
    to (action_summary, flat_metrics). action_summary replaces status + diagnostic
    as first group. entry_strategy removed from trade_snapshot (DD-3 — now in
    action_summary on VALID paths only).

    Pure mapping function. No computation, no conditionals beyond
    null-checking. Does NOT modify flat_metrics.
    """

    def _map(table):
        return {gk: flat_metrics.get(fk, None) for fk, gk in table}

    def _map_subgrouped(subgroups, scalars=None):
        out = {}
        for sg_name, sg_table in subgroups:
            out[sg_name] = _map(sg_table)
        if scalars:
            for fk, gk in scalars:
                out[gk] = flat_metrics.get(fk, None)
        return out

    # --- trade_snapshot: explicit ordering for operator readability ---
    # DIAG-001 Phase 2B (DD-3): entry_strategy REMOVED — now in action_summary (VALID only)
    # PE-42: current_price source changes for Profile A (live price supplement)
    #   bar_close_price, price_source added.
    is_etf = flat_metrics.get("Is_ETF", None)

    # BRK-001: Breakout model flag — read once, used by multiple sections below
    _brk_active = flat_metrics.get("BRK_Model_Active", False)
    _brk_model_tag = flat_metrics.get("BRK_Model_Tag")

    # PE-42: Derive current_price based on price_source
    _pe42_price_source = flat_metrics.get("Price_Source", "BAR")
    _pe42_live_price = flat_metrics.get("Live_Price")
    _pe42_bar_close  = flat_metrics.get("Bar_Close_Price")
    if _pe42_live_price is not None:
        # LIVE or DAILY_CLOSE: Live_Price is populated
        _current_price = _pe42_live_price
    elif _pe42_price_source != "BAR":
        # UNAVAILABLE: Live_Price is None, fall back to bar close
        _current_price = _pe42_bar_close
    else:
        # BAR (Profile B/C): unchanged behavior
        _current_price = flat_metrics.get("Price", None)

    # --- SNAP-001: Price source desc ---
    _price_source_descs = {
        "LIVE": "Real-time market price. Decision price is bar_close.",
        "DAILY_CLOSE": "Bar close price (post-market evaluation).",
        "STALE_CORRECTED": "Stale bar corrected with live data (PE-42).",
        "BAR": "Bar close price.",
        "UNAVAILABLE": "Live price unavailable (post-close).",
    }
    _price_source_desc = _price_source_descs.get(_pe42_price_source, "")

    # --- SNAP-001: Convexity descs ---
    _convexity_val = flat_metrics.get("Convexity_Class")
    _convexity_descs = {
        "C1": "High convexity -- defensive exit with accelerated monitoring",
        "C2": "Standard convexity -- mechanical exit at profit target",
        "C3": "Low convexity -- open-ended position with graduated exit",
        "C-1": "High convexity -- defensive exit with accelerated monitoring",
        "C-2": "Standard convexity -- mechanical exit at profit target",
        "C-3": "Low convexity -- open-ended position with graduated exit",
    }
    _convexity_desc = _convexity_descs.get(_convexity_val, "")

    # --- SNAP-001: ETF detection desc ---
    _etf_det = flat_metrics.get("ETF_Detection_Source")
    if is_etf:
        _etf_det_desc = "ETF confirmed -- profile-adjusted thresholds active"
    else:
        _etf_det_desc = "No ETF characteristics detected"

    # --- SNAP-001: Structural floor desc from anchor label ---
    _anchor_label_val = flat_metrics.get("Anchor_Label", "")
    _struct_floor_desc = _anchor_label_val if _anchor_label_val else "Structural floor"

    # --- SNAP-001: Resistance desc (profile-dynamic) ---
    _engine_state = flat_metrics.get("Engine_State", "")
    if _engine_state and "TRENDING" in _engine_state and not is_etf:
        _p_code_guess = "A" if "hourly" in str(flat_metrics.get("Data_Basis", "")).lower() or "SWING" in str(flat_metrics.get("Data_Basis", "")).upper() else "B"
    else:
        _p_code_guess = "B"
    # Approximate profile from data_basis
    _db = flat_metrics.get("Data_Basis", "")
    if "SWING" in str(_db).upper():
        _resistance_desc = "Primary-frame 10-bar high (hourly recent ceiling)"
    elif "TREND" in str(_db).upper():
        _resistance_desc = "Primary-frame 10-bar high (daily recent ceiling)"
    else:
        _resistance_desc = "Primary-frame 10-bar high"

    # --- SNAP-001: Build price_levels sub-object ---
    # AVWAP-001 DQ-7: Calendar-time coverage desc enrichment (all profiles)
    _db_raw = flat_metrics.get("Data_Basis", "")
    if "SWING" in str(_db_raw).upper():
        _desc_map = {
            "ema_8":  "Short-term trend (8-period EMA, ~1 trading day on hourly bars)",
            "ema_21": "Medium-term trend (21-period EMA, ~3 trading days on hourly bars)",
            "sma_50": "Intermediate trend support (50-period SMA, ~7 trading days on hourly bars)",
            "sma_200": "Long-term trend support (200-period SMA, ~29 trading days on hourly bars)",
        }
    elif "WEALTH" in str(_db_raw).upper():
        _desc_map = {
            "ema_8":  "Short-term trend (8-period EMA, ~2 months on weekly bars)",
            "ema_21": "Medium-term trend (21-period EMA, ~5 months on weekly bars)",
            "sma_50": "Intermediate trend support (50-period SMA, ~1 year on weekly bars)",
            "sma_200": "Long-term trend support (200-period SMA, ~4 years on weekly bars)",
        }
    else:
        _desc_map = {
            "ema_8":  "Short-term trend (8-period EMA, ~1.5 weeks on daily bars)",
            "ema_21": "Medium-term trend (21-period EMA, ~1 month on daily bars)",
            "sma_50": "Intermediate trend support (50-period SMA, ~2.5 months on daily bars)",
            "sma_200": "Long-term trend support (200-period SMA, ~10 months on daily bars)",
        }

    _price_levels = {
        "ema_8": {"price": flat_metrics.get("EMA_8"), "desc": _desc_map["ema_8"]},
        "ema_21": {"price": flat_metrics.get("EMA_21"), "desc": _desc_map["ema_21"]},
        "sma_50": {"price": flat_metrics.get("SMA_50"), "desc": _desc_map["sma_50"]},
        "sma_200": {"price": flat_metrics.get("SMA_200"), "desc": _desc_map["sma_200"]},
    }
    # VWAP: Profile A only
    _vwap_val = flat_metrics.get("VWAP")
    if _vwap_val is not None:
        _price_levels["vwap"] = {"price": _vwap_val, "desc": "Intraday institutional value level (session VWAP)"}

    # VS-15: Surface resistance note when price is at or above level
    _resistance_price = flat_metrics.get("Resistance")
    _resistance_note = flat_metrics.get("Resistance_Note")
    if _resistance_price is None and _resistance_note:
        _resistance_desc_final = _resistance_note
    elif _resistance_price is None:
        _resistance_desc_final = _resistance_desc + " (suppressed -- price at or above level)"
    else:
        _resistance_desc_final = _resistance_desc

    # BRK-001: When breakout model active, relabel resistance as new support
    _sr_note = flat_metrics.get("Support_Resistance_Note")
    if _brk_active:
        _brk_ns = flat_metrics.get("BRK_New_Support")
        _resistance_desc_final = (
            f"FLIPPED TO NEW SUPPORT: old resistance ({_resistance_price or _brk_ns}) "
            f"is now post-breakout support level"
        )
        _sr_note = (
            f"Post-breakout S/R flip active (model: BREAKOUT). "
            f"Old resistance {_resistance_price or _brk_ns} → new support. "
            f"New resistance = measured move target."
        )

    trade_snapshot = {
        "price": {
            "current": _current_price,
            "bar_close": _pe42_bar_close,
            "source": {"label": _pe42_price_source, "desc": _price_source_desc},
        },
        "structural_floor": {"price": flat_metrics.get("Structural_Floor"), "desc": _struct_floor_desc},
        "resistance": {"price": _resistance_price, "desc": _resistance_desc_final},
        "support_resistance_note": _sr_note,  # BUG-R1 / BRK-001
        "atr": {"value": flat_metrics.get("ATR"), "period": 14, "desc": "Average True Range (14-period) -- unit of measurement for distances and thresholds"},
        "avg_daily_volume": {"value": flat_metrics.get("ADV_20"), "formatted": _format_volume(flat_metrics.get("ADV_20")), "unit": "shares", "desc": "20-day average daily volume"},
        "classification": {
            "type": "ETF" if is_etf else ("EQUITY" if is_etf is not None else None),
            "convexity": {"label": _convexity_val, "desc": _convexity_desc},
            "exchange": flat_metrics.get("ETF_Primary_Exchange"),
            "etf_detection": {"label": _etf_det or "NONE", "desc": _etf_det_desc},
        },
        "price_levels": _price_levels,
    }

    # --- FA-001: Custom floor_analysis assembly ---
    _ff_status_label = flat_metrics.get("Floor_Failure_Status_Label", "CLEAR")
    _ff_status_desc = flat_metrics.get("Floor_Failure_Status_Desc", "No consecutive bars below structural floor")
    _ff_context = flat_metrics.get("Floor_Failure_Context")
    _ff_breach_dist = flat_metrics.get("Floor_Breach_Dist")
    _ff_reclaim = flat_metrics.get("Floor_Failure_Reclaim")
    _ff_threshold = flat_metrics.get("Floor_Failure_Threshold")

    # [FPC-001] Pre-compute floor_proximity_pct band before emission for clean shape
    _fp_pct_value = flat_metrics.get("Floor_Prox_Pct")
    _fp_pct_cond, _fp_pct_thr = _floor_proximity_pct_band(_fp_pct_value)

    floor_analysis = {
        "anchor": {
            "type": flat_metrics.get("Floor_Anchor_Type", flat_metrics.get("Anchor_Type")),
            "label": flat_metrics.get("Floor_Anchor_Label", ""),
            "price": flat_metrics.get("Structural_Floor"),
            "desc": flat_metrics.get("Anchor_Label", ""),
        },
        "floor_failure": {
            "status": {"label": _ff_status_label, "desc": _ff_status_desc},
            "context": {"label": _ff_context, "desc": ""} if _ff_context else None,
            "breach_distance": {"value": _ff_breach_dist, "unit": "ATR", "desc": "Distance below structural floor (negative = below)"} if _ff_breach_dist is not None else None,
            "reclaim_progress": {"value": _ff_reclaim, "desc": "Consecutive closes back above floor (3 required)"} if _ff_reclaim else None,
            "threshold": {"value": _ff_threshold, "unit": "bars", "desc": "Consecutive closes below floor to trigger failure"} if _ff_threshold else None,
        },
        # [FPC-001] floor_proximity_pct now includes condition + thresholds when value present
        "floor_proximity_pct": {
            "value": _fp_pct_value,
            "unit": "%",
            "condition": _fp_pct_cond,
            "thresholds": _fp_pct_thr,
            "desc": "Price distance from structural floor as percentage",
        } if _fp_pct_value is not None else None,
    }

    # --- FA-001: higher_frame sub-object (profile-scoped) ---
    _ctx_ema8 = flat_metrics.get("Context_EMA_8")
    _ctx_ema21 = flat_metrics.get("Context_EMA_21")
    _ctx_ema_stacked = flat_metrics.get("Context_EMA_Stacked")
    _ctx_ema_bias = flat_metrics.get("Context_EMA_Bias")
    _ctx_ema_bias_desc = flat_metrics.get("Context_EMA_Bias_Desc", "")

    # Determine timeframe from available context fields
    _has_daily = flat_metrics.get("Context_Daily_SMA50") is not None or flat_metrics.get("Context_Daily_SMA50_Slope") is not None
    _has_weekly = flat_metrics.get("Context_Weekly_SMA50") is not None
    _has_monthly = flat_metrics.get("Context_Monthly_SMA50") is not None

    if _has_daily:
        _hf_timeframe = "DAILY"
        _hf_tf_desc = "Context frame for structural regime"
        _hf_sma50_price = flat_metrics.get("Context_Daily_SMA50")
        _hf_sma50_slope = flat_metrics.get("Context_Daily_SMA50_Slope")
        _hf_sma200_price = flat_metrics.get("Context_SMA200")
        _hf_golden_cross = flat_metrics.get("Context_Golden_Cross")
        _hf_price_vs_sma200 = flat_metrics.get("Context_Price_vs_SMA200")
        # [WKC-002] Profile A higher_frame DAILY stage classification
        _hf_stage_classification = flat_metrics.get("Context_Daily_Stage_Classification")
    elif _has_weekly:
        _hf_timeframe = "WEEKLY"
        _hf_tf_desc = "Context frame for structural regime"
        _hf_sma50_price = flat_metrics.get("Context_Weekly_SMA50")
        _hf_sma50_slope = flat_metrics.get("Context_Weekly_SMA50_Slope")
        # [WKC-002] Profile B Weekly SMA 200 absolute value now available as a flat key
        _hf_sma200_price = flat_metrics.get("Context_Weekly_SMA200")
        _hf_golden_cross = flat_metrics.get("Context_Weekly_Golden_Cross")
        _hf_price_vs_sma200 = flat_metrics.get("Context_Weekly_Price_vs_SMA200")
        # [WKC-002] Profile B higher_frame WEEKLY stage classification
        _hf_stage_classification = flat_metrics.get("Context_Weekly_Stage_Classification")
    elif _has_monthly:
        _hf_timeframe = "MONTHLY"
        _hf_tf_desc = "Context frame for structural regime"
        _hf_sma50_price = flat_metrics.get("Context_Monthly_SMA50")
        _hf_sma50_slope = flat_metrics.get("Context_Monthly_SMA50_Slope")
        _hf_sma200_price = flat_metrics.get("Context_Monthly_SMA200")
        _hf_golden_cross = flat_metrics.get("Context_Monthly_Golden_Cross")
        _hf_price_vs_sma200 = flat_metrics.get("Context_Monthly_Price_vs_SMA200")
        # [WKC-002] Profile C higher_frame MONTHLY stage classification
        _hf_stage_classification = flat_metrics.get("Context_Monthly_Stage_Classification")
    else:
        _hf_timeframe = None
        _hf_tf_desc = ""
        _hf_sma50_price = None
        _hf_sma50_slope = None
        _hf_sma200_price = None
        _hf_golden_cross = None
        _hf_price_vs_sma200 = None
        _hf_stage_classification = None    # [WKC-002]

    _sma50_slope_bias = flat_metrics.get("Context_SMA50_Slope_Bias")
    _sma50_slope_bias_desc = ""
    if _sma50_slope_bias == "BULLISH":
        _sma50_slope_bias_desc = f"{_hf_timeframe or ''} SMA 50 rising".strip()
    elif _sma50_slope_bias == "BEARISH":
        _sma50_slope_bias_desc = f"{_hf_timeframe or ''} SMA 50 declining".strip()

    # [EMA50-001] Source EMA 50 price + slope from profile-specific flat keys,
    # keyed by the same _hf_timeframe triplet used for SMA 50 above. Slope
    # bias mirrors the SMA 50 derivation pattern.
    if _hf_timeframe == "DAILY":
        _hf_ema50_price = flat_metrics.get("Context_Daily_EMA_50")
        _hf_ema50_slope = flat_metrics.get("Context_Daily_EMA_50_Slope")
    elif _hf_timeframe == "WEEKLY":
        _hf_ema50_price = flat_metrics.get("Context_Weekly_EMA_50")
        _hf_ema50_slope = flat_metrics.get("Context_Weekly_EMA_50_Slope")
    elif _hf_timeframe == "MONTHLY":
        _hf_ema50_price = flat_metrics.get("Context_Monthly_EMA_50")
        _hf_ema50_slope = flat_metrics.get("Context_Monthly_EMA_50_Slope")
    else:
        _hf_ema50_price = None
        _hf_ema50_slope = None

    _ema50_slope_bias = flat_metrics.get("Context_EMA_50_Slope_Bias")
    _ema50_slope_bias_desc = ""
    if _ema50_slope_bias == "BULLISH":
        _ema50_slope_bias_desc = f"{_hf_timeframe or ''} EMA 50 rising".strip()
    elif _ema50_slope_bias == "BEARISH":
        _ema50_slope_bias_desc = f"{_hf_timeframe or ''} EMA 50 declining".strip()

    higher_frame = {}
    if _hf_timeframe:
        higher_frame["timeframe"] = {"label": _hf_timeframe, "desc": _hf_tf_desc}
        if _ctx_ema8 is not None or _ctx_ema21 is not None:
            higher_frame["ema"] = {
                "ema_8": _ctx_ema8,
                "ema_21": _ctx_ema21,
                "stacked": _ctx_ema_stacked,
                "bias": {"label": _ctx_ema_bias, "desc": _ctx_ema_bias_desc} if _ctx_ema_bias else None,
                "desc": f"{_hf_timeframe} short/medium trend structure",
            }
        if _hf_golden_cross is not None:
            higher_frame["golden_cross"] = {
                "value": _hf_golden_cross,
                "bias": "BULLISH" if _hf_golden_cross else "BEARISH",
                "desc": f"{_hf_timeframe} SMA 50 {'above' if _hf_golden_cross else 'below'} {_hf_timeframe} SMA 200",
            }
        if _hf_sma50_price is not None:
            higher_frame["sma50"] = {
                "price": _hf_sma50_price,
                "slope": {"value": _hf_sma50_slope, "unit": "dollars", "bias": {"label": _sma50_slope_bias, "desc": _sma50_slope_bias_desc}} if _hf_sma50_slope is not None else None,
                "desc": f"{_hf_timeframe} SMA 50",
            }
        # [EMA50-001] higher_frame.ema_50 grouped object -- parallel to sma50
        # above with enriched slope.desc and top-level desc per DQ-9.
        # Strictly informational; not a hierarchy anchor; not in conviction map.
        if _hf_ema50_price is not None:
            higher_frame["ema_50"] = {
                "price": _hf_ema50_price,
                "slope": {
                    "value": _hf_ema50_slope,
                    "unit": "dollars",
                    "bias": {"label": _ema50_slope_bias, "desc": _ema50_slope_bias_desc},
                    "desc": f"{_hf_timeframe} EMA 50 slope (bar-to-bar)",
                } if _hf_ema50_slope is not None else None,
                "desc": f"{_hf_timeframe} EMA 50 -- alternative medium-term reference",
            }
        if _hf_sma200_price is not None:
            # [HFI-001-B] price_distance now includes pct + condition + thresholds
            # and a timeframe-aware outer desc. Per HFI-001 design brief D2/D3/D4:
            #   DAILY   -> _daily_cyclical_elevation        (CYCLICAL_* tokens)
            #   WEEKLY  -> _macro_secular_elevation (REUSE) (SECULAR_*  tokens)
            #   MONTHLY -> _monthly_decadal_elevation       (DECADAL_*  tokens)
            # Same cutoffs (0/25/75/150/300 %) across all three per D5.
            # No new flat keys -- pct is computed on-the-fly from the existing
            # per-profile dollar + sma200 flat keys (§6 Q4 default).
            _price_distance_obj = None
            if _hf_price_vs_sma200 is not None:
                # Compute pct with division-by-zero guard, matching the
                # macro_frame.sma200 pattern at the WKC-001 v1.1 site below.
                if _hf_sma200_price and _hf_sma200_price != 0:
                    _hf_pct_above_sma200 = round((_hf_price_vs_sma200 / _hf_sma200_price) * 100.0, 2)
                else:
                    _hf_pct_above_sma200 = None
                if _hf_timeframe == "DAILY":
                    _hf_elev_cond, _hf_elev_thr = _daily_cyclical_elevation(_hf_pct_above_sma200)
                    _hf_pd_outer_desc = "DAILY close distance from DAILY SMA 200 -- intermediate cyclical reference"
                elif _hf_timeframe == "WEEKLY":
                    # D3: REUSE macro secular helper -- weekly SMA 200 is
                    # genuinely secular regardless of profile lens. Profile B
                    # weekly higher_frame == Profile A macro_frame weekly metric.
                    _hf_elev_cond, _hf_elev_thr = _macro_secular_elevation(_hf_pct_above_sma200)
                    _hf_pd_outer_desc = "WEEKLY close distance from WEEKLY SMA 200 -- secular trend reference"
                elif _hf_timeframe == "MONTHLY":
                    _hf_elev_cond, _hf_elev_thr = _monthly_decadal_elevation(_hf_pct_above_sma200)
                    _hf_pd_outer_desc = "MONTHLY close distance from MONTHLY SMA 200 -- multi-decade structural reference"
                else:
                    # Defensive fallback (should not occur given the timeframe
                    # detection block above always sets _hf_timeframe to one
                    # of the three labels when _hf_sma200_price is not None).
                    _hf_elev_cond, _hf_elev_thr = (None, None)
                    _hf_pd_outer_desc = f"{_hf_timeframe} close distance from {_hf_timeframe} SMA 200"
                _price_distance_obj = {
                    "value": _hf_price_vs_sma200,
                    "unit": "dollars",
                    "pct": _hf_pct_above_sma200,
                    "unit_pct": "%",
                    "condition": _hf_elev_cond,
                    "thresholds": _hf_elev_thr,
                    "desc": _hf_pd_outer_desc,
                }
            higher_frame["sma200"] = {
                "price": _hf_sma200_price,
                "price_distance": _price_distance_obj,
                "desc": f"{_hf_timeframe} SMA 200",
            }

        # [WKC-002] market_stage sub-object on higher_frame.
        # Mirrors macro_frame.market_stage shape from WKC-001 v1.1 with
        # timeframe-aware purpose desc (cyclical-vs-secular semantics).
        # The stage labels themselves are timeframe-agnostic per Design Lock
        # §A3 -- the enclosing higher_frame.timeframe.label provides context.
        if _hf_stage_classification is not None:
            # Compute criteria_evaluated from the underlying flat values
            # (transparent surface so operator sees the 3 truths that drove
            # the stage classification).
            # IMPORTANT: All booleans wrapped with bool() to coerce numpy.bool
            # variants to Python bool for JSON serialization. Profile B's
            # Context_Weekly_SMA50_Slope and Context_Weekly_SMA50 are written
            # in gates.py without float() wrappers, so they can be numpy
            # scalars; numpy_float > 0 returns numpy.bool which crashes
            # json.dumps with "Object of type bool is not JSON serializable".
            _hf_crit_sma50_above_sma200 = bool(_hf_golden_cross) if _hf_golden_cross is not None else None
            _hf_crit_slope_positive = bool(_hf_sma50_slope is not None
                                           and _hf_sma50_slope > 0)
            # price_above_sma50: reconstruct from sma200 + price_distance
            # (which gives close), then compare to sma50
            if (_hf_sma200_price is not None
                    and _hf_price_vs_sma200 is not None
                    and _hf_sma50_price is not None):
                _hf_close = _hf_sma200_price + _hf_price_vs_sma200
                _hf_crit_price_above_sma50 = bool(_hf_close > _hf_sma50_price)
            else:
                _hf_crit_price_above_sma50 = None

            higher_frame["market_stage"] = {
                "framework": "Weinstein 4-Stage Market Cycle",
                "framework_desc": _hf_framework_desc(),
                "desc": _hf_purpose_desc(_hf_timeframe),
                "stage": {
                    "label": _hf_stage_classification,
                    "desc": _hf_stage_desc(_hf_stage_classification, _hf_timeframe),
                },
                "criteria_evaluated": {
                    "sma50_above_sma200": _hf_crit_sma50_above_sma200,
                    "sma50_slope_positive": _hf_crit_slope_positive,
                    "price_above_sma50": _hf_crit_price_above_sma50,
                },
                "definition": "STRICT",  # [WKC-003] STRICT replaces SIMPLIFIED
                "stage_2_confirmed": bool(_hf_stage_classification == "STAGE_2_ADVANCING"),
            }

        # [UX-002] Daily ATR relocated here from the retired protective_anchor
        # section (spec §4.1, DQ-3). Profile-A only -- spec prose: "inside the
        # Profile-A (DAILY timeframe) path"; _hf_timeframe == "DAILY" is the
        # Profile-A indicator at this site (data.py:684 initialises Daily_ATR
        # to 0.0 on B/C, so the > 0 guard mirrors output.py:2597 / :3410).
        if _hf_timeframe == "DAILY":
            _daily_atr_val = flat_metrics.get("Daily_ATR")
            if _daily_atr_val is not None and _daily_atr_val > 0:
                higher_frame["daily_atr"] = {
                    "value": _daily_atr_val,
                    "unit": "price",
                    "desc": "Daily ATR(14) -- swing-frame volatility unit",
                }

    floor_analysis["higher_frame"] = higher_frame if higher_frame else None

    # [WKC-001 v1.1] Macro frame grouped emission -- Profile A only.
    # Mirrors higher_frame shape (timeframe + ema + golden_cross + sma50 +
    # sma200 + ema_50) plus market_stage sub-object (Weinstein 4-stage
    # classifier replacing the v1.0 binary stage_2). v1.1 adds bias
    # sub-objects (Group A), adx condition+thresholds (Group B1), sma200
    # price_distance pct+condition+thresholds (Group B2), and full
    # market_stage classification (Group C). None on Profile B/C.
    _macro_sma50_price = flat_metrics.get("Context_Macro_SMA_50")
    macro_frame = {}
    if _macro_sma50_price is not None:
        macro_frame["timeframe"] = {
            "label": "WEEKLY",
            "desc": "Macro frame -- advisory structural context (not a gate input)",
        }

        # EMA 8/21 sub-object (Group A: + bias)
        _macro_ema8 = flat_metrics.get("Context_Macro_EMA_8")
        _macro_ema21 = flat_metrics.get("Context_Macro_EMA_21")
        _macro_ema_stacked = flat_metrics.get("Context_Macro_EMA_Stacked")
        if _macro_ema8 is not None or _macro_ema21 is not None:
            _ema_obj = {
                "ema_8": _macro_ema8,
                "ema_21": _macro_ema21,
                "stacked": _macro_ema_stacked,
                "desc": "WEEKLY short/medium trend structure",
            }
            # Group A: bias sub-object based on stacked boolean
            if _macro_ema_stacked is not None:
                _ema_obj["bias"] = {
                    "label": "BULLISH" if _macro_ema_stacked else "BEARISH",
                    "desc": ("Weekly EMA 8 above Weekly EMA 21"
                             if _macro_ema_stacked
                             else "Weekly EMA 8 below Weekly EMA 21"),
                }
            macro_frame["ema"] = _ema_obj

        # Golden cross sub-object (unchanged from v1.0 -- already had bias)
        _macro_gc = flat_metrics.get("Context_Macro_Golden_Cross")
        if _macro_gc is not None:
            macro_frame["golden_cross"] = {
                "value": _macro_gc,
                "bias": "BULLISH" if _macro_gc else "BEARISH",
                "desc": f"WEEKLY SMA 50 {'above' if _macro_gc else 'below'} WEEKLY SMA 200",
            }

        # SMA 50 sub-object (Group A: slope gains bias sub-object)
        _macro_sma50_slope = flat_metrics.get("Context_Macro_SMA_50_Slope")
        _sma50_slope_obj = None
        if _macro_sma50_slope is not None:
            if _macro_sma50_slope > 0:
                _sma50_slope_bias = {"label": "BULLISH", "desc": "Weekly SMA 50 rising"}
            elif _macro_sma50_slope < 0:
                _sma50_slope_bias = {"label": "BEARISH", "desc": "Weekly SMA 50 falling"}
            else:
                _sma50_slope_bias = {"label": "FLAT", "desc": "Weekly SMA 50 flat"}
            _sma50_slope_obj = {
                "value": _macro_sma50_slope,
                "unit": "dollars",
                "bias": _sma50_slope_bias,
                "desc": "WEEKLY SMA 50 slope (bar-to-bar)",
            }
        macro_frame["sma50"] = {
            "price": _macro_sma50_price,
            "slope": _sma50_slope_obj,
            "desc": "WEEKLY SMA 50",
        }

        # SMA 200 sub-object (Group B2: pct + condition + thresholds added to price_distance)
        _macro_sma200_price = flat_metrics.get("Context_Macro_SMA_200")
        _macro_price_vs_sma200 = flat_metrics.get("Context_Macro_Price_vs_SMA200")
        if _macro_sma200_price is not None:
            _price_distance_obj = None
            if _macro_price_vs_sma200 is not None:
                # Compute pct above SMA 200 (Group B2 enrichment)
                if _macro_sma200_price and _macro_sma200_price != 0:
                    _pct_above_sma200 = round((_macro_price_vs_sma200 / _macro_sma200_price) * 100.0, 2)
                else:
                    _pct_above_sma200 = None
                _elev_cond, _elev_thr = _macro_secular_elevation(_pct_above_sma200)
                _price_distance_obj = {
                    "value": _macro_price_vs_sma200,
                    "unit": "dollars",
                    "pct": _pct_above_sma200,
                    "unit_pct": "%",
                    "condition": _elev_cond,
                    "thresholds": _elev_thr,
                    "desc": "WEEKLY close distance from WEEKLY SMA 200 -- secular trend reference (NOT a swing-trade extension signal)",
                }
            macro_frame["sma200"] = {
                "price": _macro_sma200_price,
                "price_distance": _price_distance_obj,
                "desc": "WEEKLY SMA 200",
            }

        # EMA 50 sub-object (Group A: slope gains bias sub-object)
        _macro_ema50_price = flat_metrics.get("Context_Macro_EMA_50")
        _macro_ema50_slope = flat_metrics.get("Context_Macro_EMA_50_Slope")
        if _macro_ema50_price is not None:
            _ema50_slope_obj = None
            if _macro_ema50_slope is not None:
                if _macro_ema50_slope > 0:
                    _ema50_slope_bias = {"label": "BULLISH", "desc": "Weekly EMA 50 rising"}
                elif _macro_ema50_slope < 0:
                    _ema50_slope_bias = {"label": "BEARISH", "desc": "Weekly EMA 50 falling"}
                else:
                    _ema50_slope_bias = {"label": "FLAT", "desc": "Weekly EMA 50 flat"}
                _ema50_slope_obj = {
                    "value": _macro_ema50_slope,
                    "unit": "dollars",
                    "bias": _ema50_slope_bias,
                    "desc": "WEEKLY EMA 50 slope (bar-to-bar)",
                }
            macro_frame["ema_50"] = {
                "price": _macro_ema50_price,
                "slope": _ema50_slope_obj,
                "desc": "WEEKLY EMA 50 -- alternative medium-term reference",
            }

        # ADX sub-object (Group B1: condition + thresholds)
        _macro_adx = flat_metrics.get("Context_Macro_ADX")
        if _macro_adx is not None:
            _adx_cond, _adx_thr = _macro_adx_condition(_macro_adx)
            macro_frame["adx"] = {
                "value": _macro_adx,
                "condition": _adx_cond,
                "thresholds": _adx_thr,
                "desc": "WEEKLY ADX(14) -- macro trend strength",
            }

        # market_stage sub-object (Group C: Weinstein 4-stage classifier).
        # Replaces v1.0 stage_2 sub-object. The boolean stage_2_confirmed
        # is preserved inside this sub-object for backward compatibility.
        _macro_stage_label = flat_metrics.get("Context_Macro_Stage_Classification")
        _macro_stage2_bool = flat_metrics.get("Context_Macro_Stage2")
        _macro_stage_def = flat_metrics.get("Context_Macro_Stage2_Definition")
        if _macro_stage_label is not None:
            # Compute criteria_evaluated from the underlying flat values
            # (transparent surface so the operator sees the 3 truths
            # that drove the stage classification).
            # IMPORTANT: All booleans wrapped with bool() to coerce numpy.bool
            # variants to Python bool for JSON serialization (defensive --
            # currently safe on Profile A because output.py uses float()
            # wrappers, but vulnerable to the same failure mode as
            # higher_frame Profile B).
            _crit_sma50_above_sma200 = bool(_macro_gc) if _macro_gc is not None else None
            _crit_slope_positive = bool(_macro_sma50_slope is not None
                                        and _macro_sma50_slope > 0)
            # price_above_sma50: derive from Context_Macro_SMA_50 vs Context_Macro_Price_vs_SMA200
            # (we don't have weekly close as a flat key; reconstruct from price_distance + sma200)
            if (_macro_sma200_price is not None
                    and _macro_price_vs_sma200 is not None
                    and _macro_sma50_price is not None):
                _macro_weekly_close = _macro_sma200_price + _macro_price_vs_sma200
                _crit_price_above_sma50 = bool(_macro_weekly_close > _macro_sma50_price)
            else:
                _crit_price_above_sma50 = None

            macro_frame["market_stage"] = {
                "framework": "Weinstein 4-Stage Market Cycle",
                "framework_desc": ("STAGE_1: Basing/Accumulation | "
                                   "STAGE_2: Advancing/Markup | "
                                   "STAGE_3: Topping/Distribution | "
                                   "STAGE_4: Declining/Markdown"),
                "desc": ("Long-horizon structural classification -- identifies which "
                         "phase of the cyclical advance/decline this stock currently "
                         "occupies. Used to filter for ideal long-side entry candidates "
                         "(Stage 2), avoid structural traps (Stage 3 topping, Stage 4 "
                         "declining), and recognize potential early-stage opportunities "
                         "(Stage 1 basing)."),
                "stage": {
                    "label": _macro_stage_label,
                    "desc": _macro_stage_desc(_macro_stage_label),
                },
                "criteria_evaluated": {
                    "sma50_above_sma200": _crit_sma50_above_sma200,
                    "sma50_slope_positive": _crit_slope_positive,
                    "price_above_sma50": _crit_price_above_sma50,
                },
                "definition": _macro_stage_def,
                "stage_2_confirmed": _macro_stage2_bool,
            }

    floor_analysis["macro_frame"] = macro_frame if macro_frame else None

    # [UX-002] PA-001's `floor_analysis.protective_anchor` group removed
    # (spec §4.3a). The `price` field duplicated `higher_frame.ema.ema_21`,
    # the `hard_stop` field duplicated the DAILY_HARD_STOP stop-hierarchy
    # entry, and the orphaned `daily_atr` relocated to `higher_frame.daily_atr`
    # above (Change 1). Flat keys retained; reverse map re-homed in _flatten().

    # PA-001 Phase 2 Step 3e: PE-CAL-3 exemption in floor_analysis
    _pe_cal3_exempt = flat_metrics.get("Floor_Proximity_Exempted")
    if _pe_cal3_exempt:
        floor_analysis["floor_proximity_exemption"] = {
            "exempted": True,
            "desc": flat_metrics.get("Floor_Proximity_Exemption_Desc", "Floor proximity hard-stop substitution exempted for Profile A"),
        }

    # === SelfDoc Batch 1: Custom object assembly ===

    # --- THS-002: Self-documenting trend_health ---
    _tq = _map_subgrouped(_TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS)
    _tq["trend_health"] = {
        "score": {
            "value": flat_metrics.get("Trend_Health_Score"),
            "max": 100,
            "label": flat_metrics.get("THS_Label"),
            "desc": "Weighted composite of all sub-scores",
        },
        "threshold": {
            "value": 50,
            "max": 100,
            "desc": "Minimum score for VALID verdict",
        },
        "floor_buffer": {
            "value": flat_metrics.get("THS_Floor_Buffer"),
            "max": 100,
            "label": flat_metrics.get("THS_Floor_Buffer_Label"),
            "desc": "ATR cushion above structural floor",
        },
        "dir_momentum": {
            "value": flat_metrics.get("THS_Dir_Momentum"),
            "max": 100,
            "label": flat_metrics.get("THS_Dir_Momentum_Label"),
            "desc": "ADX strength + bullish DI spread",
        },
        "trend_age": {
            "value": flat_metrics.get("THS_Trend_Age"),
            "max": 100,
            "label": flat_metrics.get("THS_Trend_Age_Label"),
            "desc": "Bars remaining in execution window",
        },
        "structure": {
            "value": flat_metrics.get("THS_Structure"),
            "max": 100,
            "label": flat_metrics.get("THS_Structure_Label"),
            "desc": "MA stack integrity + EMA separation",
        },
        "advisory": {
            "death_cross_cap": {
                "active": bool(flat_metrics.get("THS_Death_Cross_Cap", False)),
                "desc": "Primary-frame death cross (SMA 50 < SMA 200) caps THS at 50 -- Profile B/C only",
            },
            "component_cap": {
                "active": flat_metrics.get("THS_Component_Cap") is not None,
                "trigger": flat_metrics.get("THS_Component_Cap"),
                "desc": "Critical sub-score (DM < 40 or SQ < 40) caps THS at 50",
            },
            "vwap_penalty": {
                "active": bool(flat_metrics.get("THS_VWAP_Floor_Penalty", False)),
                "note": flat_metrics.get("THS_VWAP_Floor_Note"),
                "desc": "VWAP floor persistence penalty (FB x 0.5) -- Profile A only",
            },
            "context_warning": {
                "message": flat_metrics.get("THS_Context_Advisory"),
                "desc": "Context-frame structural advisory (bearish EMA bias, declining SMA slope)",
            },
        },
    }

    # --- VOL-003: Self-documenting volume ---
    _poc_dist_atr = flat_metrics.get("Vol_PoC_Distance_ATR")
    _avwap_dist_atr = flat_metrics.get("AVWAP_Distance_ATR")
    _tq["volume"] = {
        "summary": {
            "label": flat_metrics.get("Vol_Summary_Label") or flat_metrics.get("Volume_Context_Label"),
            "bias": flat_metrics.get("Vol_Summary_Bias"),
            "confidence": flat_metrics.get("Vol_Summary_Confidence"),
            "detail": flat_metrics.get("Vol_Summary_Detail"),
            "desc": "Synthesis of all volume signals",
        },
        "rvol": {
            "value": flat_metrics.get("RVOL_Value"),
            "label": flat_metrics.get("RVOL_Label"),
            "desc": "Current bar volume vs 20-bar average volume",
        },
        "bar_volume": {
            "value": flat_metrics.get("Bar_Volume"),
            "formatted": _format_volume(flat_metrics.get("Bar_Volume")),
            "desc": "Volume of the evaluated bar",
        },
        "session_volume": {
            "value": flat_metrics.get("Session_Volume"),
            "formatted": _format_volume(flat_metrics.get("Session_Volume")),
            "desc": "Cumulative session volume at engine execution time (Profile A only)",
        } if flat_metrics.get("Session_Volume") is not None else None,
        "confirmation_ratio": {
            "value": flat_metrics.get("Vol_Confirm_Ratio"),
            "max": 1.0,
            "label": flat_metrics.get("Vol_Confirm_State"),
            "bias": flat_metrics.get("Vol_Confirm_Bias"),
            "desc": "High-volume up-bars vs total high-volume bars (10-bar window)",
        },
        "poc": {
            "price": flat_metrics.get("Vol_PoC_Price"),
            "distance_atr": {"value": _poc_dist_atr, "threshold": 0.25, "desc": "ATR distance from price to highest-volume level"} if _poc_dist_atr is not None else None,
            "position": flat_metrics.get("Vol_PoC_Position"),
            "bias": flat_metrics.get("PoC_Bias"),
            "bias_desc": flat_metrics.get("PoC_Bias_Desc"),
            "period": flat_metrics.get("Vol_Histogram_Period"),
            "desc": "Highest-volume price level (IBKR histogram)",
        },
        "avwap": {
            "price": flat_metrics.get("AVWAP_Price"),
            "distance_atr": {"value": _avwap_dist_atr, "threshold": 0.25, "desc": "ATR distance from price to institutional avg cost"} if _avwap_dist_atr is not None else None,
            "position": flat_metrics.get("AVWAP_Position"),
            "bias": flat_metrics.get("AVWAP_Bias"),
            "bias_desc": flat_metrics.get("AVWAP_Bias_Desc"),
            "desc": "Volume-weighted average cost (10-bar window)",
        },
        "avg_daily_dollar_volume": {"value": flat_metrics.get("ADV_20_Dollar"), "formatted": _format_dollar_volume(flat_metrics.get("ADV_20_Dollar")), "unit": "USD", "desc": "20-day average daily dollar volume"},
    }

    # --- AVWAP-001 DQ-6: Session VWAP informational context (Profile A only) ---
    _svwap_bias = flat_metrics.get("Session_VWAP_Bias")
    if _svwap_bias is not None:
        _tq["vwap_context"] = {
            "price": flat_metrics.get("VWAP"),
            "bias": {
                "label": _svwap_bias,
                "desc": flat_metrics.get("Session_VWAP_Bias_Desc", ""),
            },
            "distance_atr": {
                "value": flat_metrics.get("Session_VWAP_Distance_ATR"),
                "unit": "ATR",
                "desc": "Distance from price to session VWAP in hourly ATR units",
            },
            "advisory": {
                "label": flat_metrics.get("Session_VWAP_Advisory"),
                "desc": flat_metrics.get("Session_VWAP_Advisory_Desc", ""),
            },
            "role": "INFORMATIONAL -- Session VWAP is no longer a structural anchor. Used for intraday sentiment and fill quality advisory.",
        }

    # --- TS-001: Self-documenting trend_state ---
    # Classification: state, age_bars, modifiers, churn
    _churn_raw = flat_metrics.get("Inst_Churn", "")
    if _churn_raw and _churn_raw.startswith("ACTIVE"):
        _churn_label = "ACTIVE"
        _churn_desc = "High-volume indecision at extended levels -- distribution warning"
    elif _churn_raw and _churn_raw.startswith("INFORMATIONAL"):
        _churn_label = "INFORMATIONAL"
        _churn_desc = "High-volume indecision at extended levels -- C-3 exempt, no action mandated"
    else:
        _churn_label = "CLEAR"
        _churn_desc = "No high-volume indecision at extended levels"

    _mods_list = flat_metrics.get("Active_Modifiers_List", [])

    _ts_classification = {
        "state": {
            "label": flat_metrics.get("Engine_State"),
            "desc": flat_metrics.get("Engine_State_Desc", ""),
        },
        "age_bars": {
            "value": flat_metrics.get("Trend_Age_Bars"),
            "max": flat_metrics.get("Trend_Age_Max"),
            "desc": "Bars consumed in execution window",
        },
        "modifiers": {
            "active": _mods_list if _mods_list else [],
            "desc": "Bar-shape patterns on evaluated bar (A: Rejection, B: Ignition, C: Compression)",
        },
        "churn": {
            "label": _churn_label,
            "desc": _churn_desc,
        },
    }

    # Directional: adx, accel, di
    _adx_accel_val = flat_metrics.get("ADX_Accel")
    _adx_accel_state = flat_metrics.get("ADX_Accel_State", "")
    _accel_desc_map = {
        "ACCELERATING": "Rising ADX momentum (ACCELERATING > 0.3 | CRUISING | DECELERATING < -0.3)",
        "CRUISING": "Near-flat ADX momentum (ACCELERATING > 0.3 | CRUISING | DECELERATING < -0.3)",
        "DECELERATING": "Falling ADX momentum (ACCELERATING > 0.3 | CRUISING | DECELERATING < -0.3)",
    }

    _di_spread = flat_metrics.get("DI_Spread")
    _di_bias = flat_metrics.get("DI_Bias", "NEUTRAL")
    _di_bias_descs = {
        "BULLISH": "DI+ exceeds DI- -- buyers control direction",
        "BEARISH": "DI- exceeds DI+ -- sellers control direction",
        "NEUTRAL": "DI+ equals DI- -- no directional dominance",
    }

    # [HFI-001-A] Pre-compute primary-frame ADX band before emission for clean
    # shape. Profile -> primary timeframe mapping uses the same Data_Basis
    # substring discriminator as the existing _p_code_guess block above
    # (SWING -> Profile A hourly, TREND -> Profile B daily, WEALTH -> Profile C
    # weekly). See HFI-001 design brief §3 for the desc-text contract.
    _adx_value = flat_metrics.get("ADX")
    _data_basis_upper = str(flat_metrics.get("Data_Basis", "")).upper()
    if "SWING" in _data_basis_upper:
        _primary_tf_label = "Hourly"
    elif "TREND" in _data_basis_upper:
        _primary_tf_label = "Daily"
    elif "WEALTH" in _data_basis_upper:
        _primary_tf_label = "Weekly"
    else:
        _primary_tf_label = "Primary"  # defensive fallback; helper handles this
    _primary_adx_cond, _primary_adx_thr = _primary_adx_condition(_adx_value, _primary_tf_label)

    _ts_directional = {
        "adx": {
            "value": _adx_value,
            "threshold": 20,
            "condition": _primary_adx_cond,
            "thresholds": _primary_adx_thr,
            "desc": "Trend strength (state boundary)",
        },
        "accel": {
            "rate": {
                "value": _adx_accel_val,
                "threshold": 0.3,
                "desc": "ADX rate of change",
            },
            "state": {
                "label": _adx_accel_state,
                "desc": _accel_desc_map.get(_adx_accel_state, ""),
            },
        },
        "di": {
            "plus": flat_metrics.get("DI_Plus"),
            "minus": flat_metrics.get("DI_Minus"),
            "spread": _di_spread,
            "bias": {
                "label": _di_bias,
                "desc": _di_bias_descs.get(_di_bias, ""),
            },
            "desc": "Directional index (positive spread = bullish)",
        },
    }

    trend_state = {
        "classification": _ts_classification,
        "directional": _ts_directional,
    }

    # --- RISK-001: Self-documenting trade_risk ---
    _rr_val = flat_metrics.get("Reward_Risk")
    _exp_threshold = flat_metrics.get("Expectancy_Threshold")
    _exp_threshold_note = flat_metrics.get("Expectancy_Threshold_Note")
    _crr_val = flat_metrics.get("Capital_Reward_Risk")
    _crr_label_val = flat_metrics.get("Capital_RR_Label")
    # [BUGR-003] Pre-compute Capital_RR_Role up here so it is available to the
    # capital_reward_risk.status assembly below. Previously read only at
    # line ~1083 for the capital_rr_role attachment; now read once here and
    # reused. Spec §4.2.4.
    _cap_rr_role = flat_metrics.get("Capital_RR_Role")
    _cap_rr_role_desc = flat_metrics.get("Capital_RR_Role_Desc")

    _crr_status_desc_map = {
        "HEALTHY": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
        "NARROW": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
        "INSUFFICIENT": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
    }

    # RISK-UX-001: Five-label summary (absorbs complete flag + risk_per_unit)
    _risk_summary_label = flat_metrics.get("Risk_Summary_Label")
    _risk_summary_desc = flat_metrics.get("Risk_Summary_Desc")
    _rpu = flat_metrics.get("Risk_Per_Unit")

    if _risk_summary_label is not None:
        # Full assessment — FAVORABLE / ADEQUATE / UNFAVORABLE
        _summary_label = _risk_summary_label
        _summary_desc = _risk_summary_desc
    elif _crr_val is not None:
        # Partial — capital R:R available but price R:R not computed.
        # [BUGR-003] On Profile A ADVISORY paths, emit "(ADVISORY -- informational)"
        # parenthetical in place of the threshold tier label so PARTIAL summary
        # desc stops leaking the enforcement-ladder label on paths where no
        # enforcement threshold applies. Spec §4.2.4.
        _summary_label = "PARTIAL"
        if _cap_rr_role == "ADVISORY":
            _summary_desc = (
                f"Capital R:R {_crr_val:.2f} (ADVISORY -- informational). "
                f"Price R:R not computed on this path."
            )
        else:
            _summary_desc = f"Capital R:R {_crr_val:.2f} ({_crr_label_val}). Price R:R not computed on this path."
    else:
        # No data
        _summary_label = "NOT_AVAILABLE"
        _summary_desc = "Risk assessment requires structural floor intact and valid entry path"

    trade_risk = {
        "summary": {
            "label": _summary_label,
            "risk_per_unit": {"value": _rpu, "desc": "Dollar risk per share (price minus hard stop)"} if _rpu is not None else None,
            "desc": _summary_desc,
        },
        "price_reward_risk": {
            "value": _rr_val,
            "threshold": {
                "value": _exp_threshold if _exp_threshold is not None else 2.0,
                "note": _exp_threshold_note,
                "desc": "Minimum structural R:R -- below: INVALID, at or above: entry permitted",
            },
            "note": flat_metrics.get("Reward_Risk_Note"),
            # [BUGR-004] reward numerator is trade_setup.target.price, not resistance
            # (differs when PE-41 escalates to WEEKLY_RESISTANCE or RWD-001 blue-sky
            # fires ATR_PROJECTION / MEASURED_MOVE). Static desc refers operators to
            # the authoritative target.source field rather than duplicating per-source
            # prose here. Spec §4.3.4.
            # [OUT-002] Conditional desc by model — BRK-active uses tight stop; non-BRK uses structural floor
            "desc": (
                "Price R:R -- reward (profit target - price) / risk (price - tight stop). "
                "See trade_setup.target.source for target origin."
            ) if _brk_active else (
                "Price R:R -- reward (profit target - price) / risk (price - structural floor). "
                "See trade_setup.target.source for target origin."
            ),
        },
        "capital_reward_risk": {
            "value": _crr_val,
            # [BUGR-003] On Profile A, Capital_RR_Role == "ADVISORY" (set at
            # output.py:1620-1622). The enforcement-ladder label
            # (HEALTHY/NARROW/INSUFFICIENT) does not apply — INSUFFICIENT in
            # particular would imply entry is blocked, which contradicts the
            # sibling capital_rr_role.label (correctly ADVISORY). Null the
            # status.label and emit an explanatory desc that points operators
            # at capital_rr_role.desc for rationale. Non-ADVISORY paths are
            # unchanged. Spec §4.2.4, DQ #1 resolution option (a).
            "status": {
                "label": None if _cap_rr_role == "ADVISORY" else _crr_label_val,
                "desc": (
                    "Advisory only -- no enforcement threshold applied on Profile A. "
                    "See capital_rr_role.desc for rationale."
                    if _cap_rr_role == "ADVISORY"
                    else _crr_status_desc_map.get(_crr_label_val or "", "")
                ),
            },
            "desc": "Capital R:R -- reward (target - price) / risk (price - hard stop)",
        },
        # FRR-001 → RISK-UX-001: Fundamental R:R restructured (Profile B only, null on A/C)
        "fundamental_reward_risk": {
            "value": flat_metrics.get("Fundamental_RR"),
            "label": flat_metrics.get("Fundamental_RR_Label"),
            "analyst_levels": {
                "target": flat_metrics.get("Fundamental_Target"),
                "floor": flat_metrics.get("Fundamental_Floor"),
                "ceiling": flat_metrics.get("Fundamental_Target_High"),
                "coverage": flat_metrics.get("Fundamental_Analyst_Count"),
                "desc": "Institutional price levels -- analyst consensus 12-month targets (median / low / high)",
            } if flat_metrics.get("Fundamental_Target") is not None else None,
            "advisory": flat_metrics.get("Fundamental_RR_Note"),
            "desc": "Fundamental R:R -- reward (analyst median - price) / risk (price - analyst low)",
        },
    }

    # PA-001 Phase 2 Step 3c: Capital R:R advisory role annotation.
    # [BUGR-003] _cap_rr_role / _cap_rr_role_desc were pre-computed earlier
    # (see block above _crr_status_desc_map) so the capital_reward_risk.status
    # assembly can apply the ADVISORY conditional. Attachment below is unchanged.
    if _cap_rr_role:
        trade_risk["capital_rr_role"] = {"label": _cap_rr_role, "desc": _cap_rr_role_desc or ""}
    # BRK-001: Add model tag to trade_risk when breakout model active
    if _brk_active and _brk_model_tag:
        trade_risk["model"] = _brk_model_tag

    # --- PROX-001: Self-documenting entry_proximity ---
    _prox_signal = flat_metrics.get("Proximity_Signal")
    if _prox_signal == "APPROACHING":
        _prox_signal_desc = (
            "One condition from valid entry -- all structural checks pass"
        )
        entry_proximity = {
            "signal": {
                "label": "APPROACHING",
                "desc": _prox_signal_desc,
            },
            "blocking_condition": {
                "label": flat_metrics.get("Proximity_Condition_Label"),
                "desc": flat_metrics.get("Proximity_Condition_Desc", ""),
            },
            "distance": {
                "value": flat_metrics.get("Proximity_Distance"),
                "unit": flat_metrics.get("Proximity_Distance_Unit", "ATR"),
                "desc": "Distance to valid entry condition",
            },
            "target": {
                "value": flat_metrics.get("Proximity_Target"),
                "desc": "Pullback zone upper bound",
            },
            "note": flat_metrics.get("Proximity_Note"),
        }
    else:
        # Inactive collapse: only signal field
        entry_proximity = {
            "signal": {
                "label": "NONE",
                "desc": "No entry condition approaching -- multiple structural conditions unmet",
            },
        }

    # --- EXIT-001: Self-documenting exit_signals ---
    _exit_sig = flat_metrics.get("Exit_Signal", "CLEAR")
    _exit_sig_descs = {
        "CLEAR": "No exit condition active",
        "WARNING": "Early deterioration -- single trigger active, no mechanical action mandated",
        "EXIT": "Structural break -- mechanical exit mandated",
    }
    _exit_triggers_raw = flat_metrics.get("Exit_Triggers")
    _exit_triggers = _exit_triggers_raw if isinstance(_exit_triggers_raw, list) else []

    exit_signals = {
        "signal": {
            "label": _exit_sig if _exit_sig else "CLEAR",
            "desc": _exit_sig_descs.get(_exit_sig or "CLEAR", ""),
        },
        "triggers": _exit_triggers,
        "reason": flat_metrics.get("Exit_Reason"),
    }

    # Profile-scoped fields
    _ema21_counter = flat_metrics.get("Exit_EMA21_Counter")
    if _ema21_counter is not None:
        _ema21_int = int(_ema21_counter.split("/")[0]) if isinstance(_ema21_counter, str) and "/" in _ema21_counter else _ema21_counter
        exit_signals["ema21_counter"] = {
            "value": _ema21_int,
            "threshold": 3,
            "desc": "Consecutive closes below EMA 21 structural floor (3 triggers EXIT)",
        }
    _ema8_counter = flat_metrics.get("Exit_EMA8_Counter")
    if _ema8_counter is not None:
        # Parse "0/2" -> integer 0
        _ema8_int = int(_ema8_counter.split("/")[0]) if isinstance(_ema8_counter, str) and "/" in _ema8_counter else _ema8_counter
        exit_signals["ema8_counter"] = {
            "value": _ema8_int,
            "threshold": 2,
            "desc": "Consecutive closes below EMA 8 (2 triggers EXIT)",
        }
    _est_low = flat_metrics.get("Established_Hourly_Low")
    if _est_low is not None:
        exit_signals["established_low"] = {
            "price": _est_low,
            "desc": "10-bar completed low (close below triggers WARNING)",
        }

    # --- Assemble in operator reading order ---

    # --- SETUP-001: Custom trade_setup assembly ---
    _profit_target = flat_metrics.get("Profit_Target")
    _profit_target_source = flat_metrics.get("Profit_Target_Source")
    _profit_target_role = flat_metrics.get("Profit_Target_Role")
    _hard_stop = flat_metrics.get("Hard_Stop")
    _original_stop = flat_metrics.get("Original_Hard_Stop")
    _stop_adjusted = flat_metrics.get("Stop_Adjusted_Flag")
    _stop_reason = flat_metrics.get("Stop_Adjusted_Reason")

    # Target role desc per convexity
    _role_descs = {
        "PRESCRIPTIVE": "Mechanical exit at this level",
        "INFORMATIONAL": "Reference level only -- no mechanical exit (open-ended reward)",
    }
    _role_label = "COMPULSORY" if _profit_target_role == "PRESCRIPTIVE" else ("INFORMATIONAL" if _profit_target_role == "INFORMATIONAL" else _profit_target_role)
    _role_desc = _role_descs.get(_profit_target_role, "Mechanical exit at this level")

    # RISK-UX-001: Intermediate as structured object
    _intermediate_val = flat_metrics.get("Profit_Target_Synthetic")
    _intermediate_obj = None
    if _intermediate_val is not None:
        _intermediate_obj = {
            "price": _intermediate_val,
            "method": "Floor + 1.5 ATR",
            "desc": "Risk-calibrated partial exit level for pullback entries",
        }

    # RISK-UX-001: Blue sky relocated from trade_risk to trade_setup.target
    _bs_detected = flat_metrics.get("Blue_Sky_Detected", False)
    _blue_sky_obj = None
    if _bs_detected:
        _bs_method = flat_metrics.get("Blue_Sky_Method")
        _bs_method_desc_map = {
            "ATR_PROJECTION": "Target derived from ATR projection -- asset above all historical resistance",
            "MEASURED_MOVE": "Target derived from measured move -- prior rally leg projection exceeds ATR projection",
        }
        _blue_sky_obj = {
            "detected": True,
            "method": _bs_method,
            "atr_headroom": flat_metrics.get("Blue_Sky_ATR_Headroom"),
            "desc": _bs_method_desc_map.get(_bs_method, "Blue-sky condition detected"),
        }

    _target_obj = {
        "price": _profit_target,
        "source": {"label": _profit_target_source, "desc": _profit_target_source or ""},
        "role": {"label": _role_label, "desc": _role_desc} if _profit_target_role else None,
        "intermediate": _intermediate_obj,
        "blue_sky": _blue_sky_obj,
    } if _profit_target is not None else (
        # FRR-001: Preserve source/role even when Profit_Target price is None
        # (e.g. FLOOR BREACH path with fundamental R:R active).
        {
            "price": None,
            "source": {"label": _profit_target_source, "desc": _profit_target_source or ""},
            "role": {"label": _role_label, "desc": _role_desc} if _profit_target_role else None,
            "intermediate": None,
            "blue_sky": None,
        } if _profit_target_source or _profit_target_role else None
    )
    # BRK-001: Add model tag to target when breakout model active
    if _brk_active and _brk_model_tag and _target_obj is not None:
        _target_obj["model"] = _brk_model_tag

    _stop_proximity_blocked = flat_metrics.get("Stop_Proximity_Blocked", False)
    _stop_gap_atr = flat_metrics.get("Stop_Gap_ATR")

    _stop_adj = None
    if _stop_adjusted:
        _stop_adj = {
            "original_price": _original_stop,
            "adjusted": True,
            "proximity_blocked": False,
            "gap_atr": _stop_gap_atr,
            "reason": _stop_reason,
            "desc": f"Structural stop audit -- stop adjusted for {(_stop_reason or 'proximity').split('--')[0].strip().lower()}",
        }
    elif _stop_proximity_blocked:
        _stop_adj = {
            "original_price": _original_stop or _hard_stop,
            "adjusted": False,
            "proximity_blocked": True,
            "gap_atr": _stop_gap_atr,
            "reason": _stop_reason,
            "desc": "Structural stop audit -- proximity qualifier blocked adjustment (wide gap)",
        }

    _stop_obj = {
        "price": _hard_stop,
        "note": flat_metrics.get("Hard_Stop_Note"),
        "desc": (
            flat_metrics.get("Hard_Stop_Note") or "Breakout support - ATR buffer (thesis invalidation level)"
        ) if _brk_active else "Floor - 1.5 ATR (maximum loss level)",
        "adjustment": _stop_adj,
    }
    if _brk_active and _brk_model_tag:
        _stop_obj["model"] = _brk_model_tag

    # Entry zone (evaluation-path aware -- BUGR-005/007 cleaner-alternative refactor).
    # Keyed off the effective evaluation protocol that produced R:R, stop, and
    # target on this run, NOT off Window_Reset_Event alone (which carries the
    # historical trigger and remains stale on thesis-failure / window-expiry
    # fallback paths). Spec §3.1, §4.4.4(B).
    _entry_ref = flat_metrics.get("Entry_Reference")
    _pb_upper = flat_metrics.get("Pullback_Zone_Upper")
    _window_reset = flat_metrics.get("Window_Reset_Event", "")
    _trigger_type = _window_reset.split(" + ")[0] if _window_reset else ""

    # Historical trigger type (from Window_Reset_Event). Distinct from the
    # effective evaluation protocol on fallback paths (see _render_as_pullback_fallback).
    _is_pullback = _trigger_type.upper() == "PULLBACK" if _trigger_type else False
    _is_breakout_hist = _trigger_type.upper() == "BREAKOUT" if _trigger_type else False
    _is_reclaim = _trigger_type.upper() == "RECLAIM" if _trigger_type else False

    # BUGR-005 + BUGR-007: detect fallback to pullback-frame rendering.
    # The effective evaluation protocol is PULLBACK when the historical
    # trigger was BREAKOUT but the breakout model did not run -- either
    # thesis-failure fallback (BRK-001-GAP-2 fires, _brk_active goes False)
    # OR thesis-success + window-expiry without BRK activation (_brk_active
    # False, Breakout_Thesis_Status non-FAILED). In either case R:R, stop,
    # and target were produced by standard pullback evaluation; entry_zone
    # must reflect that, not the dormant historical trigger.
    _thesis_failed = flat_metrics.get("Breakout_Thesis_Status") == "FAILED"
    _brk_breakout_fallback = _is_breakout_hist and not _brk_active
    _render_as_pullback_fallback = _thesis_failed or _brk_breakout_fallback

    # VS-17: reference.desc per effective evaluation protocol.
    if _render_as_pullback_fallback:
        _ref_desc = flat_metrics.get("Entry_Zone_Reference") or flat_metrics.get("Anchor_Label", "")
    elif _is_pullback:
        _ref_desc = flat_metrics.get("Entry_Zone_Reference") or flat_metrics.get("Anchor_Label", "")
    elif _is_breakout_hist:
        # _brk_active is True here; fallback above would have caught the
        # historical-trigger-without-active-model case.
        _ref_desc = "Breakout evaluation price (completed bar close)"
    elif _is_reclaim:
        _ref_desc = "Structural floor (reclaim target)"
    else:
        _ref_desc = ""

    # VS-17: entry_zone.desc per trigger and profile
    _db = flat_metrics.get("Data_Basis", "")
    if "SWING" in str(_db).upper():
        _ez_bar_label = "hourly bar"
    elif "WEALTH" in str(_db).upper():
        _ez_bar_label = "weekly bar"
    else:
        _ez_bar_label = "daily bar"

    if _render_as_pullback_fallback:
        _ez_desc = "Close within pullback zone (" + _ez_bar_label + ")"
    elif _is_pullback:
        _ez_desc = "Close within pullback zone (" + _ez_bar_label + ")"
    elif _is_breakout_hist and _brk_active:
        # BRK-001: Breakout entry zone description with hold-above guidance
        _brk_ns = flat_metrics.get("BRK_New_Support")
        _ez_desc = (
            f"Close above resistance (confirmed breakout). "
            f"Enter on next bar if price holds above {_brk_ns}."
        ) if _brk_ns else "Close above resistance (confirmed breakout)"
    elif _is_reclaim:
        _ez_desc = "Close above structural floor (3 bars required)" if _ez_bar_label != "weekly bar" else ""
    else:
        _ez_desc = ""

    # VS-09: entry_price_range.desc per profile
    if "SWING" in str(_db).upper():
        _epr_desc = "Daily EMA 21 ± 0.5 daily ATR (Action Zone)"
    elif "WEALTH" in str(_db).upper():
        _epr_desc = "Floor to floor + 0.5 ATR"
    else:
        _epr_desc = "Floor to EMA 21 + 0.5 ATR"

    # BUGR-005 + BUGR-007: effective trigger label. On fallback paths the
    # trigger renders as PULLBACK (matching the actual evaluation protocol);
    # on all other paths the historical trigger is preserved.
    if _render_as_pullback_fallback:
        _effective_trigger = "PULLBACK"
    else:
        _effective_trigger = _trigger_type if _trigger_type else None

    # VS-14: entry_price_range only on native PULLBACK triggers (not fallbacks).
    # Pullback_Zone_Upper is derived for the native PULLBACK trigger path;
    # on fallback paths the historical-window bounds do not apply.
    # VS-04: Guard for EMA inversion on broken structures.
    # [EZR-001] _ez_inverted intentionally keeps comparing the structural floor
    # (_entry_ref) against _pb_upper. The §A3.2 fix is display-only and must NOT
    # reassign _entry_ref: re-sourcing it to the Daily EMA 21 would make this
    # guard compare Daily_EMA_21 > (Daily_EMA_21 + 0.5*ATR) — always False —
    # silently disabling the inversion signal (Addendum 1 §A2.2 open item 1).
    _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)

    # [EZR-001] Profile A PULLBACK display alignment (Addendum 1 §A3.2).
    # The AVWAP-001 entry zone the engine gates on is Daily EMA 21 ± 0.5 ATR
    # (trigger.py:79-99), but the displayed reference.price / entry_price_range.lower
    # still showed the residual hourly-EMA-21 structural floor (_entry_ref), diverging
    # from the desc and zone bounds (both Daily-EMA-21-based). Re-source the DISPLAYED
    # values only — _entry_ref is left untouched, preserving _ez_inverted (above) and
    # the entry_strategy.entry_price consumer at output.py:2525. Profile A (SWING) only;
    # RECLAIM / breakout / Profile B / Profile C fall through to _entry_ref unchanged.
    _is_profile_a = "SWING" in str(_db).upper()
    _daily_anchor = flat_metrics.get("Daily_Protective_Anchor")  # Daily EMA 21 (display-scaled)
    _pb_lower = flat_metrics.get("Pullback_Zone_Lower")          # Daily EMA 21 - 0.5*ATR
    # reference.price: native PULLBACK or fallback-pullback, null-guarded (anchor > 0,
    # else fall back to structural floor — §A2.2 within-Profile-A fallback).
    if (_is_profile_a and (_is_pullback or _render_as_pullback_fallback)
            and _daily_anchor is not None and _daily_anchor > 0):
        _ref_price = _daily_anchor
        _ref_price_is_daily_anchor = True  # [EZR-001-OBS-1] gate for the desc override below
    else:
        _ref_price = _entry_ref
        _ref_price_is_daily_anchor = False
    # entry_price_range.lower: native PULLBACK only (range not rendered on fallback);
    # Pullback_Zone_Lower holds the hourly-ANCHOR value when daily data is unavailable,
    # so it is correct in both cases.
    if _is_profile_a and _is_pullback and _pb_lower:
        _range_lower = _pb_lower
    else:
        _range_lower = _entry_ref

    if _ref_price_is_daily_anchor:
        # [EZR-001-OBS-1] desc must match the re-sourced Daily-EMA-21 price; on
        # Entry_Zone_Reference-absent (verdict-gate early-return) paths the desc
        # would otherwise fall back to the hourly Anchor_Label. Literal mirrors
        # trigger.py:96 (Entry_Zone_Reference = "Daily EMA 21").
        _ref_desc = flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"

    _entry_zone = {
        "trigger": _effective_trigger,
        "reference": {"price": _ref_price, "desc": _ref_desc} if _ref_price else None,
        "entry_price_range": {
            "lower": _range_lower,
            "upper": _pb_upper,
            "desc": _epr_desc,
        } if (_pb_upper and _is_pullback and not _ez_inverted) else None,
        "desc": _ez_desc + " [INVERTED: EMA structure broken]" if (_is_pullback and _ez_inverted) else _ez_desc,
    }
    # BRK-001: Add minimum_hold for breakout entries (Spec §4.10)
    if _brk_active and _is_breakout_hist:
        _brk_ns = flat_metrics.get("BRK_New_Support")
        _entry_zone["minimum_hold"] = _brk_ns
        _entry_zone["entry_price_range"] = None  # breakout has no bounded zone

    # Rally (Profile A SWING + B TRENDING non-ETF only)
    _fib_382 = flat_metrics.get("Fib_A_382_Level") or flat_metrics.get("Fib_382_Level")
    _fib_500 = flat_metrics.get("Fib_A_500_Level") or flat_metrics.get("Fib_500_Level")
    _fib_conf = flat_metrics.get("Fib_A_Confluence") or flat_metrics.get("Fib_Confluence")
    _mm_target = flat_metrics.get("MM_Target")
    _mm_rally_atr = flat_metrics.get("MM_Rally_ATR")
    # [ENG-006] Fibonacci extension projection levels (display-scaled or None)
    _fib_ext_1272 = flat_metrics.get("Fib_Ext_1272_Level")
    _fib_ext_1618 = flat_metrics.get("Fib_Ext_1618_Level")
    _fib_ext_2618 = flat_metrics.get("Fib_Ext_2618_Level")

    # PE-44: Confluence desc lookup — trigger × label
    _confluence_desc_map = {
        ("PULLBACK", "CONFLUENCE_382"): "Institutional floor -- 38.2% support aligned with structural floor",
        ("PULLBACK", "CONFLUENCE_500"): "Institutional floor -- 50% support aligned with structural floor",
        ("PULLBACK", "ABOVE_FIBS"): "Above institutional support -- shallow pullback, support levels below",
        ("PULLBACK", "BETWEEN_FIBS"): "Caution -- past first institutional support, 50% support below",
        ("PULLBACK", "BELOW_FIBS"): "Warning -- price below both institutional support levels, no Fibonacci confluence",
        ("RECLAIM", "CONFLUENCE_382"): "Warning -- recovery at 38.2% institutional resistance, sellers likely at this level",
        ("RECLAIM", "CONFLUENCE_500"): "Warning -- recovery at 50% institutional resistance, sellers likely at this level",
        ("RECLAIM", "ABOVE_FIBS"): "Cleared -- price above both institutional resistance levels, Fibonacci headwinds behind",
        ("RECLAIM", "BETWEEN_FIBS"): "Caution -- recovery between institutional resistance levels, 50% resistance overhead",
        ("RECLAIM", "BELOW_FIBS"): "Early recovery -- institutional resistance zones still above, room to advance",
    }

    if _is_breakout_hist:
        _conf_label = None
        _conf_desc = "Fibonacci not applicable -- price above prior rally peak"
    else:
        _conf_label = _fib_conf
        _trig_upper = _trigger_type.upper() if _trigger_type else ""
        _conf_desc = _confluence_desc_map.get((_trig_upper, _fib_conf), f"Fibonacci confluence: {_fib_conf}")

    _rally_obj = None
    if (_fib_382 is not None or _fib_500 is not None or _mm_target is not None
            or _fib_ext_1272 is not None or _fib_ext_1618 is not None
            or _fib_ext_2618 is not None):
        # RALLY-TRIG-001: confluence.trigger_historical reflects the historical
        # Window_Reset_Event (BREAKOUT/PULLBACK/RECLAIM), distinct from
        # entry_zone.trigger which reflects the effective evaluation protocol
        # on fallback paths (1E semantics). Aligns with execution_window.trigger_historical
        # precedent at line ~1554.
        _rally_obj = {
            "confluence": {
                "trigger_historical": _trigger_type,
                "label": _conf_label,
                "desc": _conf_desc,
            },
            "fibonacci_levels": {
                "level_382": {"price": _fib_382, "desc": "38.2% -- shallow pullback boundary"} if _fib_382 else None,
                "level_500": {"price": _fib_500, "desc": "50% -- deep pullback boundary"} if _fib_500 else None,
            } if (_fib_382 is not None or _fib_500 is not None) else None,
            "projected_move": {
                "price": _mm_target,
                "desc": "Measured move target -- next leg equals prior rally",
            } if _mm_target else None,
            # [ENG-006] Forward Fibonacci extension projections from the
            # structural floor (127.2% / 161.8% / 261.8%). Informational only.
            "extensions": {
                "ext_1272": {"price": _fib_ext_1272, "desc": "127.2% extension -- forward projection from structural floor"} if _fib_ext_1272 is not None else None,
                "ext_1618": {"price": _fib_ext_1618, "desc": "161.8% extension -- golden-ratio forward projection from structural floor"} if _fib_ext_1618 is not None else None,
                "ext_2618": {"price": _fib_ext_2618, "desc": "261.8% extension -- forward projection from structural floor"} if _fib_ext_2618 is not None else None,
            } if (_fib_ext_1272 is not None or _fib_ext_1618 is not None or _fib_ext_2618 is not None) else None,
        }

    # Execution window
    _wc = flat_metrics.get("window_count")
    _wl = flat_metrics.get("Window_Limit")

    # VS-05: Detect the 99 sentinel (no trigger ever recorded)
    _is_sentinel = (_wc is not None and _wc == 99)

    # VS-13: timeframe from profile
    if "SWING" in str(_db).upper():
        _ew_timeframe = "hour"
    elif "WEALTH" in str(_db).upper():
        _ew_timeframe = "week"
    else:
        _ew_timeframe = "day"

    # VS-05: Status and desc conditional on sentinel
    if _is_sentinel:
        _ew_status = "NO_TRIGGER"
        _ew_current = None
        _ew_desc = "No trigger event recorded"
    else:
        _ew_status = "EXPIRED" if (_wc is not None and _wl is not None and _wc >= _wl) else "OPEN"
        _ew_current = _wc
        _ew_desc = f"{_wc} of {_wl} bars elapsed since {_window_reset}" if _wc is not None and _wl else ""

    # VS-10: Flag historical trigger when state has changed since trigger
    _trigger_historical = False
    if _trigger_type and not _is_sentinel:
        if _trigger_type.upper() == "BREAKOUT" and "TRENDING" in _engine_state.upper():
            _trigger_historical = True

    _exec_window = {
        "current": _ew_current,
        "limit": _wl if not _is_sentinel else None,
        "unit": "bars",
        "timeframe": _ew_timeframe,
        "status": _ew_status,
        "reset_event": _window_reset if not _is_sentinel else None,
        "desc": _ew_desc,
        "trigger_historical": _trigger_historical if _trigger_historical else None,
        "trigger_note": "Trigger occurred during prior RESOLVING state" if _trigger_historical else None,
    }

    trade_setup = {
        "target": _target_obj,
        "stop": _stop_obj,
        "entry_zone": _entry_zone,
        "rally": _rally_obj,
        "execution_window": _exec_window,
    }

    # --- EXT-001: Custom extension_analysis assembly ---
    _atr_dist = flat_metrics.get("ATR_Dist")
    _atr_anchor = flat_metrics.get("ATR_Dist_Anchor")
    _ext_limit = flat_metrics.get("Extension_Limit")
    _anchor_type_label = flat_metrics.get("Extension_Anchor_Label", "")
    _anchor_canonical = flat_metrics.get("Extension_Anchor_Type", _atr_anchor)
    _tq_override = flat_metrics.get("Trend_Quality_Override")

    _override_obj = None
    if _tq_override and isinstance(_tq_override, dict):
        _override_obj = _tq_override
    else:
        _override_obj = {
            "eligible": False,
            "reason": flat_metrics.get("ATR_Dist_Note") or "",
            "note": "Extension is protective. Do not chase.",
        }

    _eff_limit = flat_metrics.get("Extension_Limit_Effective")
    _ext_exempt_note = flat_metrics.get("Extension_Exemption_Note")

    # EXT-OBS-001: Extension distance condition label
    if _atr_dist is None:
        _ext_condition = {"label": None, "desc": "Extension distance not available"}
    else:
        _eff_lim_val = _eff_limit if _eff_limit is not None else _ext_limit
        if _eff_lim_val is not None and _atr_dist > _eff_lim_val:
            _ext_condition = {"label": "OVEREXTENDED", "desc": "Warning -- price stretched beyond entry limit"}
        elif _atr_dist >= 1.0:
            _ext_condition = {"label": "ELEVATED", "desc": "Caution -- approaching extension limit, stop distance increasing"}
        elif _atr_dist >= 0.25:
            _ext_condition = {"label": "NORMAL", "desc": "Healthy distance from structural floor"}
        elif _atr_dist >= -0.25:
            _ext_condition = {"label": "AT_FLOOR", "desc": "Optimal -- price at or near structural floor, tight stop distance"}
        else:
            _ext_condition = {"label": "BELOW_FLOOR", "desc": "Warning -- price below structural anchor"}

    _floor_anchor_for_ext = flat_metrics.get("Floor_Anchor_Type", "")

    if _floor_anchor_for_ext == "EMA_21":
        # Profile A: intraday extension RETIRED (AVWAP-001 DQ-4)
        extension_analysis = {
            "intraday_retired": True,
            "intraday_retired_note": "Intraday extension gate retired for Profile A -- PA-001 daily extension gate is sole overextension check",
        }
    else:
        # Profile B/C: existing intraday extension analysis (unchanged)
        extension_analysis = {
            "distance": {"value": _atr_dist, "unit": "ATR", "desc": "Distance from structural anchor (positive = above)"},
            "anchor": {"label": _anchor_canonical, "desc": _anchor_type_label},
            "limit": {
                "value": _ext_limit,
                "effective": _eff_limit if _eff_limit is not None else _ext_limit,
                "unit": "ATR",
                "desc": "Maximum distance for valid entry -- beyond this: overextended",
                "exemption": _ext_exempt_note,
            },
            "override": _override_obj,
            "condition": _ext_condition,
        }

    # PA-001 Phase 2 Step 3a: Daily extension overlay (Profile A only)
    _daily_ext_dist = flat_metrics.get("Daily_Extension_Distance")
    _daily_ext_label = flat_metrics.get("Daily_Extension_Label")
    _daily_ext_caution = flat_metrics.get("Daily_Extension_Caution_Note")

    _daily_extension = None
    if _daily_ext_dist is not None:
        _daily_ext_desc_map = {
            "NORMAL": "Within normal swing range from daily EMA 21",
            "CAUTION": "Elevated -- monitor for exhaustion signs (Power Overbought zone)",
            "EXHAUSTION": "Overextended -- beyond sustainable swing distance (hard reject)",
        }
        # [PCT-001] Compute percentage-distance parallel metric. Sibling to
        # existing ATR-unit distance per DQ-6. No %-thresholds introduced --
        # Profile A daily EMA 21 has no research-grounded % thresholds in
        # PCT-001 scope (DQ-8 scope guard).
        _daily_ext_dist_pct = None
        _daily_ema21_price = flat_metrics.get("Context_EMA_21")
        _daily_close = flat_metrics.get("Price")
        if _daily_ema21_price is not None and _daily_ema21_price > 0 and _daily_close is not None:
            _daily_ext_dist_pct = round((float(_daily_close) - float(_daily_ema21_price)) / float(_daily_ema21_price) * 100.0, 2)
        _daily_extension = {
            "distance": {"value": _daily_ext_dist, "unit": "ATR", "desc": "Distance from Daily EMA 21 in daily ATR units"},
            "distance_pct": {"value": _daily_ext_dist_pct, "unit": "%", "desc": "Percentage distance from Daily EMA 21"},  # [PCT-001]
            "anchor": {"label": "EMA_21", "desc": "Daily 21-period exponential moving average (protective anchor)"},
            "condition": {"label": _daily_ext_label, "desc": _daily_ext_desc_map.get(_daily_ext_label, "")},
            "thresholds": {
                "caution": {"value": 2.0, "unit": "ATR", "desc": "Advisory caution level"},
                "exhaustion": {"value": 3.0, "unit": "ATR", "desc": "Hard reject level"},
            },
        }
        if _daily_ext_caution:
            _daily_extension["caution_note"] = _daily_ext_caution

        # PA-001 Phase 2 Step 3d: Daily RSI advisory nested in daily extension
        _daily_rsi = flat_metrics.get("Daily_RSI")
        _rsi_admissibility = flat_metrics.get("Daily_RSI_Admissibility")
        _rsi_admissibility_desc = flat_metrics.get("Daily_RSI_Admissibility_Desc")

        if _daily_rsi is not None:
            _rsi_condition = "OVERBOUGHT" if _daily_rsi > 70 else ("OVERSOLD" if _daily_rsi < 30 else "NEUTRAL")
            _rsi_cond_desc = {
                "OVERBOUGHT": "RSI above 70 -- momentum exhaustion risk, confirms overextension",
                "OVERSOLD": "RSI below 30 -- potential reversal zone",
                "NEUTRAL": "RSI in normal range",
            }
            _daily_extension["rsi"] = {
                "value": {"value": round(_daily_rsi, 2), "unit": "index", "desc": "Daily RSI(14) -- 14-period Relative Strength Index"},
                "condition": {"label": _rsi_condition, "desc": _rsi_cond_desc.get(_rsi_condition, "")},
                "admissibility": {"label": _rsi_admissibility or "ALLOWED", "desc": _rsi_admissibility_desc or ""},
                "role": "ADVISORY -- not a gate. Surfaced for Operator awareness. Revisit gating after 3-6 months live data.",
            }

    extension_analysis["daily"] = _daily_extension

    # PA-001 DQ-11: Medium-term overextension (Profile B only)
    _mt_ext_pct = flat_metrics.get("MediumTerm_Extension_Pct")
    _mt_ext_label = flat_metrics.get("MediumTerm_Extension_Label")
    _mt_ext_caution = flat_metrics.get("MediumTerm_Extension_Caution_Note")

    _medium_term_extension = None
    if _mt_ext_pct is not None:
        _mt_desc_map = {
            "NORMAL": "Within normal medium-term range relative to SMA 50",
            "CAUTION": "Elevated -- stock may be approaching medium-term exhaustion",
            "EXHAUSTION": "Overextended -- beyond sustainable medium-term distance (hard reject)",
        }
        _medium_term_extension = {
            "distance": {"value": _mt_ext_pct, "unit": "%", "desc": "Percentage distance above SMA 50"},
            "anchor": {"label": "SMA_50", "desc": "50-day simple moving average (institutional medium-term floor)"},
            "condition": {"label": _mt_ext_label, "desc": _mt_desc_map.get(_mt_ext_label, "")},
            "thresholds": {
                "caution": {"value": 15.0, "unit": "%", "desc": "Advisory caution level"},
                "exhaustion": {"value": 25.0, "unit": "%", "desc": "Hard reject level"},
            },
        }
        if _mt_ext_caution:
            _medium_term_extension["caution_note"] = _mt_ext_caution

    # [PCT-001] Profile A medium-term extension block -- informational
    # percentage distance from Daily SMA 50. Structurally simpler than
    # Profile B equivalent (no condition, no thresholds -- DQ-8). Profile B
    # block above remains the authoritative reference for the Profile B
    # path; this block only runs on Profile A. Profile detection uses
    # _floor_anchor_for_ext == "EMA_21" since _p_code is not yet defined
    # at this point in transform.py.
    if _floor_anchor_for_ext == "EMA_21" and _medium_term_extension is None:
        _a_sma50_price = flat_metrics.get("Context_Daily_SMA50")
        _a_close = flat_metrics.get("Price")
        _a_mt_dist_pct = None
        if _a_sma50_price is not None and _a_sma50_price > 0 and _a_close is not None:
            _a_mt_dist_pct = round((float(_a_close) - float(_a_sma50_price)) / float(_a_sma50_price) * 100.0, 2)
        if _a_mt_dist_pct is not None:
            # [PCT-001 OD-3] Industry-convention interpretation band -- informational only.
            _a_mt_interp_label, _a_mt_interp_desc = _derive_medium_term_interpretation(_a_mt_dist_pct)
            _medium_term_extension = {
                "distance": {"value": _a_mt_dist_pct, "unit": "%", "desc": "Percentage distance above Daily SMA 50 (Profile A informational)"},
                "anchor": {"label": "SMA_50", "desc": "Daily 50-period simple moving average (institutional intermediate reference)"},
                "interpretation": {
                    "label": _a_mt_interp_label,
                    "desc": _a_mt_interp_desc,
                } if _a_mt_interp_label is not None else None,
            }

    extension_analysis["medium_term"] = _medium_term_extension

    # --- PSY-002: Custom psychological_levels assembly ---
    _psy_floor = flat_metrics.get("Psych_Floor")
    _psy_ceiling = flat_metrics.get("Psych_Ceiling")
    _psy_floor_dist = flat_metrics.get("Psych_Floor_Dist_Pct")
    _psy_ceiling_dist = flat_metrics.get("Psych_Ceiling_Dist_Pct")
    _psy_near_struct = flat_metrics.get("Psych_Floor_Near_Structural", flat_metrics.get("Psych_Floor_Near_Technical"))
    _psy_ceil_near = flat_metrics.get("Psych_Ceiling_Near_Technical")
    _psy_increment = flat_metrics.get("Psych_Increment")
    _rn_target = flat_metrics.get("RN_Target_Proximity")
    _rn_stop = flat_metrics.get("RN_Stop_Proximity")
    _rn_floor = flat_metrics.get("RN_Floor_Proximity")

    def _rn_label_desc(val, context):
        if val is None:
            return {"label": "CLEAR", "desc": f"No round number within proximity of {context}"}
        if val == "CLEAR":
            return {"label": "CLEAR", "desc": f"No round number within proximity of {context}"}
        return {"label": str(val), "desc": f"Round number near {context}"}

    psychological_levels = {
        "desc": "Round number support/resistance levels and their proximity to trade-critical prices",
        "increment": {"value": _psy_increment, "unit": "dollars", "desc": "Round number spacing at current price level"} if _psy_increment else None,
        "floor": {
            "price": _psy_floor,
            "distance_pct": _psy_floor_dist,
            "near_structural_floor": _psy_near_struct,
            "desc": "Nearest round number below current price",
        },
        "ceiling": {
            "price": _psy_ceiling,
            "distance_pct": _psy_ceiling_dist,
            "near_resistance": _psy_ceil_near,
            "desc": "Nearest round number above current price",
        },
        "at_target": _rn_label_desc(_rn_target, "profit target"),
        "at_stop": _rn_label_desc(_rn_stop, "hard stop"),
        "at_floor": _rn_label_desc(_rn_floor, "structural floor"),
    }

    # ==================================================================
    # PA-001 Phase 3 — DQ-9: Target Hierarchy (price ascending)
    # Pure output restructuring — zero gate logic changes.
    # ==================================================================
    _current_price = flat_metrics.get("Price")
    _profit_target = flat_metrics.get("Profit_Target")
    _profit_target_source = flat_metrics.get("Profit_Target_Source") or ""

    _target_entries = []

    # Tier 1: Daily High (10-bar daily high from context chart)
    # [DSP-003] Read the pre-override daily Tier 1 value emitted by
    # compute.py so the DAILY_HIGH row label matches its value on all
    # Profile A paths (DAILY_CTX, PE-41 WEEKLY escalation, RWD-001
    # blue-sky, BRK-001 MM override). Falls back to Resistance when the
    # new key is absent:
    #   - Profile B: primary frame == context frame, so Resistance ≡
    #     daily 10-bar high by construction.
    #   - Profile A FALLBACK_HOURLY: df_ctx unavailable — Resistance is
    #     the only available reference on this degraded defensive path.
    _tier1 = flat_metrics.get("Daily_Cons_High_Pre_Override")
    if _tier1 is None:
        _tier1 = flat_metrics.get("Resistance")
    if _tier1 is not None:
        _target_entries.append({
            "price": _tier1,
            "label": "DAILY_HIGH",
            "role": {"label": "RESISTANCE", "desc": "10-bar daily high from context chart"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _tier1) else "ACTIVE",
            "escalation_winner": bool(_profit_target is not None and abs(_tier1 - _profit_target) < 0.01),
        })

    # Tier 2: Weekly Equivalent (50-bar daily high via PE-41 escalation)
    if "WEEKLY" in _profit_target_source.upper() and _profit_target is not None:
        _target_entries.append({
            "price": _profit_target,
            "label": "WEEKLY_HIGH",
            "role": {"label": "RESISTANCE", "desc": "50-bar daily high -- PE-41 escalation (price above daily range)"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _profit_target) else "ACTIVE",
            "escalation_winner": True,
        })

    # Measured Move (AB=CD projection)
    _mm = flat_metrics.get("MM_Target")
    if _mm is not None:
        _target_entries.append({
            "price": _mm,
            "label": "MEASURED_MOVE",
            "role": {"label": "PROJECTION", "desc": "AB=CD measured move -- prior rally leg projection"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _mm) else "ACTIVE",
            "escalation_winner": bool(_profit_target is not None and abs(_mm - _profit_target) < 0.01),
        })

    # ATR Projection (Blue Sky via RWD-001)
    _bs_target = flat_metrics.get("Blue_Sky_Target")
    _bs_method = flat_metrics.get("Blue_Sky_Method")
    if _bs_target is not None and _bs_method == "ATR_PROJECTION":
        _target_entries.append({
            "price": _bs_target,
            "label": "ATR_PROJECTION",
            "role": {"label": "PROJECTION", "desc": "RWD-001 blue sky -- floor + N x Daily ATR projection"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _bs_target) else "ACTIVE",
            "escalation_winner": bool(_profit_target is not None and abs(_bs_target - _profit_target) < 0.01),
        })

    # [ENG-006] Fibonacci extension projections (127.2% / 161.8% / 261.8%).
    # Appended after the MEASURED_MOVE / ATR_PROJECTION rows (semantic grouping
    # with the other forward projections). Append position is immaterial to final
    # ordering: BUGR-002 removed the pre-partition sort and both partitioned
    # arrays are sorted ascending by price post-partition, so each row sorts into
    # correct ascending position automatically. NON-GATE: informational rows that
    # never become Profit_Target / Profit_Target_Source; escalation_winner is
    # False unless an extension exactly equals the active Profit_Target.
    for _ext_price, _ext_label, _ext_pct in (
        (flat_metrics.get("Fib_Ext_1272_Level"), "FIB_EXTENSION_1272", "127.2%"),
        (flat_metrics.get("Fib_Ext_1618_Level"), "FIB_EXTENSION_1618", "161.8%"),
        (flat_metrics.get("Fib_Ext_2618_Level"), "FIB_EXTENSION_2618", "261.8%"),
    ):
        if _ext_price is not None:
            _target_entries.append({
                "price": _ext_price,
                "label": _ext_label,
                "role": {"label": "PROJECTION",
                         "desc": f"Fibonacci {_ext_pct} extension -- forward projection from structural floor"},
                "status": "EXCEEDED" if (_current_price is not None and _current_price > _ext_price) else "ACTIVE",
                "escalation_winner": bool(_profit_target is not None and abs(_ext_price - _profit_target) < 0.01),
            })

    # Analyst Target (FRR-001 consensus median)
    _analyst = flat_metrics.get("Fundamental_Target")
    if _analyst is not None:
        _target_entries.append({
            "price": _analyst,
            "label": "ANALYST_CONSENSUS",
            "role": {"label": "FUNDAMENTAL", "desc": "FRR-001 analyst consensus median price target"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _analyst) else "ACTIVE",
            "escalation_winner": bool(_profit_target is not None and abs(_analyst - _profit_target) < 0.01),
        })

    # Psychological Ceiling (PSY-001 nearest round number above price)
    if _psy_ceiling is not None:
        _target_entries.append({
            "price": _psy_ceiling,
            "label": "PSYCHOLOGICAL",
            "role": {"label": "PSYCHOLOGICAL", "desc": "Nearest round number above current price"},
            "status": "EXCEEDED" if (_current_price is not None and _current_price > _psy_ceiling) else "ACTIVE",
            "escalation_winner": bool(_profit_target is not None and abs(_psy_ceiling - _profit_target) < 0.01),
        })

    # [CNV-001] Annotate target entries with conviction_tier + conviction_rank
    # BEFORE BRK-active scoping. Annotation propagates through the BRK filter
    # (which only reassigns escalation_winner and filters by price) and through
    # the BUGR-002 partition (which operates on price and only strips status).
    _annotate_conviction(_target_entries)

    # [BUGR-002] Pre-partition sort removed. Post-partition sorts apply
    # per §4.8: _targets_above ascending (preserves prior semantic),
    # _cleared ascending (preserves convention — EXCEEDED rows rendered
    # in same order as if they were future targets, for operator familiarity).

    # ==================================================================
    # BRK-001: TARGET HIERARCHY SCOPING (Spec §4.5)
    #
    # When breakout model active, show only levels between entry and
    # new resistance (measured move).  The old 10-bar high (DAILY_HIGH)
    # is excluded because it is now the new support.  Measured move is
    # the escalation winner.  Intermediate levels between entry and
    # measured move are kept.  Psychological levels above entry included.
    # ==================================================================
    if _brk_active:
        _brk_ns_price = flat_metrics.get("BRK_New_Support")
        _brk_scoped_targets = []
        for _te in _target_entries:
            # Exclude old resistance (now new support) — DAILY_HIGH at new support price
            if _te["label"] == "DAILY_HIGH" and _brk_ns_price is not None:
                if _te["price"] is not None and abs(_te["price"] - _brk_ns_price) < 0.02:
                    continue  # Skip: old resistance = new support
            # Keep levels between entry and measured move (or above entry for psych levels)
            if _current_price is not None and _te["price"] is not None and _te["price"] > _current_price:
                _brk_scoped_targets.append(_te)
        # Ensure measured move is marked as escalation_winner
        for _te in _brk_scoped_targets:
            if _te["label"] == "MEASURED_MOVE":
                _te["escalation_winner"] = True
            elif _te.get("escalation_winner"):
                _te["escalation_winner"] = False  # Demote non-MM winners
        _target_entries = _brk_scoped_targets

    # ==================================================================
    # [BUGR-002] Target-side partition (Spec §4.1, §4.7, §4.8, §5.2)
    #
    # Partition _target_entries using current_price predicate:
    #   hierarchy       = entries with price >  current_price (above — actual targets)
    #   cleared_levels  = entries with price <= current_price (below — EXCEEDED)
    #
    # Sorts: both ascending per §4.8. Hierarchy preserves prior semantic;
    # cleared_levels preserves the ascending convention so EXCEEDED rows render
    # in the same order as if they were future targets, for operator familiarity.
    #
    # Per §4.7: retain status field on BOTH arrays (ACTIVE in hierarchy, EXCEEDED
    # in cleared_levels — both construction-guaranteed). Retain escalation_winner
    # on BOTH — GAP-3c edge cases where a winner lands in cleared_levels remain
    # possible and are handled upstream in compute.py (out of scope per §3.2).
    #
    # Guard: when _current_price is None, fall back to pre-partition behaviour
    # — keep all entries in hierarchy, emit cleared_levels as null.
    #
    # BRK-001-active path: the BRK block above already filters
    # _te["price"] > _current_price at line 1788 and reassigns escalation_winner.
    # Post-filter, _target_entries contains only above-current rows; all land in
    # _targets_above; _cleared empty -> null per §4.6. BRK-001 §4.5 preserved.
    # ==================================================================
    if _current_price is not None:
        _targets_above = [
            te for te in _target_entries
            if te.get("price") is not None and te["price"] > _current_price
        ]
        _cleared = [
            te for te in _target_entries
            if te.get("price") is not None and te["price"] <= _current_price
        ]
    else:
        _targets_above = list(_target_entries)
        _cleared = []

    _targets_above.sort(key=lambda x: x["price"])
    _cleared.sort(key=lambda x: x["price"])

    # [CFL-001] Annotate target hierarchy entries with `confluence` on
    # clustered entries (within 0.5x ATR adjacency). Runs POST-partition so
    # only `_targets_above` is scanned — `_cleared` is intentionally excluded
    # per spec §2.2 / §5.3 (cleared_levels confluence deferred to v1.1
    # candidate CFL-001-OBS-1). Runs POST-sort so the greedy adjacent walk
    # operates on sorted prices. See CFL-001 hand-back §5 for the call-site
    # deviation rationale (the spec's §4.1 location was pre-partition/pre-sort).
    _detect_level_confluence(
        _targets_above,
        flat_metrics.get("ATR"),
        _CFL_TARGET_THRESHOLD_ATR_MULT,
        "target",
    )

    # ITS-001: Per-field lookback_stale annotation (Spec §4.6 / DQ-1a hybrid).
    # Annotate DAILY_HIGH (10-bar daily resistance) when a global intraday
    # event sits inside the field's 10-bar lookback window. Hierarchy entries
    # only; cleared_levels (already EXCEEDED) are intentionally excluded.
    if flat_metrics.get("Intraday_Lookback_Stale") is True:
        for _entry in _targets_above:
            if _entry.get("label") == "DAILY_HIGH":
                _entry["lookback_stale"] = True

    target_hierarchy = _targets_above if _targets_above else None
    target_cleared_levels = _cleared if _cleared else None

    # ==================================================================
    # PA-001 Phase 3 — DQ-10: Floor Hierarchy (price descending)
    # Pure output restructuring — zero gate logic changes.
    # ==================================================================

    # Infer profile from Floor_Anchor_Type for role assignment
    _floor_anchor_type = flat_metrics.get("Floor_Anchor_Type", "")
    if _floor_anchor_type in ("VWAP", "EMA_21"):
        _p_code = "A"
    elif _floor_anchor_type == "SMA_50":
        _p_code = "B"
    elif _floor_anchor_type == "SMA_200":
        _p_code = "C"
    else:
        _p_code = "A"  # default

    _floor_entries = []

    # Session VWAP: retained as INTRADAY_REFERENCE (AVWAP-001 DQ-6)
    _svwap_price = flat_metrics.get("VWAP")
    if _floor_anchor_type == "EMA_21" and _svwap_price is not None:
        _floor_entries.append({
            "price": _svwap_price,
            "label": "SESSION_VWAP",
            "role": {"label": "INTRADAY_REFERENCE", "desc": "Intraday bias indicator -- no longer structural anchor, resets at session open"},
            "status": "BELOW" if (_current_price is not None and _current_price < _svwap_price) else "ABOVE",
        })

    # AVWAP (10-bar rolling anchored VWAP)
    _avwap = flat_metrics.get("AVWAP_Price")
    if _avwap is not None:
        _floor_entries.append({
            "price": _avwap,
            "label": "AVWAP_10BAR",
            "role": {"label": "SUPPORT", "desc": "10-bar anchored VWAP -- institutional avg cost reference"},
            "status": "BREACHED" if (_current_price is not None and _current_price < _avwap) else "HOLDING",
        })

    # Daily EMA 21 — source resolution by profile
    # Profile A: Daily_Protective_Anchor (PA-001 daily EMA 21)
    # Profile B: EMA_21 (primary chart IS daily)
    # Profile C: Context_EMA_21 (monthly EMA 21, best available) or EMA_21 (weekly)
    _ema21_price = None
    if _p_code == "A":
        _ema21_price = flat_metrics.get("Daily_Protective_Anchor") or flat_metrics.get("Context_EMA_21")
    elif _p_code == "B":
        _ema21_price = flat_metrics.get("EMA_21")
    else:
        _ema21_price = flat_metrics.get("Context_EMA_21") or flat_metrics.get("EMA_21")

    _ema21_role_map = {"A": "PROTECTIVE_ANCHOR", "B": "SUPPORT", "C": "SUPPORT"}
    _ema21_desc_map = {
        "A": "Daily EMA 21 -- swing-frame protective floor (PA-001 dual anchor)",
        "B": "Daily EMA 21 -- medium-term trend support",
        "C": "Higher-frame EMA 21 -- trend support reference",
    }
    # [DSP-004-OBS-2] Profile-aware label map mirroring _sma50_label_map (L3337) /
    # _sma200_label_map (L3367) closed pattern. Profile C primary frame is weekly
    # per PA-001, so the EMA 21 anchor on Profile C is the higher-frame EMA 21
    # (matches _ema21_desc_map[C] = "Higher-frame EMA 21 -- trend support reference"
    # already encoded above). Profile A/B retain DAILY_EMA_21. Default
    # "DAILY_EMA_21" matches the _p_code defensive fallback convention.
    _ema21_label_map = {"A": "DAILY_EMA_21", "B": "DAILY_EMA_21", "C": "WEEKLY_EMA_21"}
    if _ema21_price is not None:
        _floor_entries.append({
            "price": _ema21_price,
            "label": _ema21_label_map.get(_p_code, "DAILY_EMA_21"),
            "role": {"label": _ema21_role_map.get(_p_code, "SUPPORT"), "desc": _ema21_desc_map.get(_p_code, "")},
            "status": "BREACHED" if (_current_price is not None and _current_price < _ema21_price) else "HOLDING",
        })

    # Daily SMA 50 — source resolution by profile
    # Profile A: Context_Daily_SMA50 (from daily context chart)
    # Profile B: SMA_50 (primary daily chart — this IS the structural floor)
    # Profile C: SMA_50 (primary weekly chart — weekly SMA 50)
    _sma50_price = None
    if _p_code == "A":
        _sma50_price = flat_metrics.get("Context_Daily_SMA50") or flat_metrics.get("SMA_50")
    else:
        _sma50_price = flat_metrics.get("SMA_50")

    _sma50_role_map = {"A": "SUPPORT", "B": "FLOOR", "C": "SUPPORT"}
    _sma50_desc_map = {
        "A": "Daily SMA 50 -- intermediate institutional trend line",
        "B": "Daily SMA 50 -- structural floor (Profile B anchor)",
        "C": "Weekly SMA 50 -- intermediate support reference",
    }
    # DSP-004: Profile-aware label map. Profile C primary frame is weekly per
    # PA-001, so the SMA 50 anchor on Profile C is the weekly SMA 50 (matches
    # _sma50_desc_map[C]). Profile A/B retain DAILY_SMA_50. Default
    # "DAILY_SMA_50" matches the _p_code defensive fallback at line 1918
    # (unknown profile → "A").
    _sma50_label_map = {"A": "DAILY_SMA_50", "B": "DAILY_SMA_50", "C": "WEEKLY_SMA_50"}
    if _sma50_price is not None:
        _floor_entries.append({
            "price": _sma50_price,
            "label": _sma50_label_map.get(_p_code, "DAILY_SMA_50"),
            "role": {"label": _sma50_role_map.get(_p_code, "SUPPORT"), "desc": _sma50_desc_map.get(_p_code, "")},
            "status": "BREACHED" if (_current_price is not None and _current_price < _sma50_price) else "HOLDING",
        })

    # Daily SMA 200 — source resolution by profile
    # Profile A: Context_SMA200 (from daily context chart)
    # Profile B: SMA_200 (primary daily chart)
    # Profile C: SMA_200 (primary weekly chart — this IS the structural floor)
    _sma200_price = None
    if _p_code == "A":
        _sma200_price = flat_metrics.get("Context_SMA200") or flat_metrics.get("SMA_200")
    else:
        _sma200_price = flat_metrics.get("SMA_200")

    _sma200_role_map = {"A": "SUPPORT", "B": "SUPPORT", "C": "FLOOR"}
    _sma200_desc_map = {
        "A": "Daily SMA 200 -- long-term secular trend floor",
        "B": "Daily SMA 200 -- long-term support reference",
        "C": "Weekly SMA 200 -- structural floor (Profile C anchor)",
    }
    # DSP-004: Profile-aware label map. Profile C primary frame is weekly per
    # PA-001, so the SMA 200 anchor on Profile C is the weekly SMA 200 — the
    # structural floor itself (role.label = FLOOR, matches _sma200_desc_map[C]).
    # Profile A/B retain DAILY_SMA_200. Default matches _p_code defensive
    # fallback at line 1918.
    _sma200_label_map = {"A": "DAILY_SMA_200", "B": "DAILY_SMA_200", "C": "WEEKLY_SMA_200"}
    if _sma200_price is not None:
        _floor_entries.append({
            "price": _sma200_price,
            "label": _sma200_label_map.get(_p_code, "DAILY_SMA_200"),
            "role": {"label": _sma200_role_map.get(_p_code, "SUPPORT"), "desc": _sma200_desc_map.get(_p_code, "")},
            "status": "BREACHED" if (_current_price is not None and _current_price < _sma200_price) else "HOLDING",
        })

    # Established Low (10-bar completed hourly low — exit trigger)
    _est_low_price = flat_metrics.get("Established_Hourly_Low")
    if _est_low_price is not None:
        _floor_entries.append({
            "price": _est_low_price,
            "label": "ESTABLISHED_LOW",
            "role": {"label": "EXIT_TRIGGER", "desc": "10-bar completed low -- break below triggers exit evaluation"},
            "status": "BREACHED" if (_current_price is not None and _current_price < _est_low_price) else "HOLDING",
        })

    # Hard Stop (intraday catastrophic stop — floor - 1.5x hourly ATR)
    _hard_stop_val = flat_metrics.get("Hard_Stop")
    if _hard_stop_val is not None:
        _floor_entries.append({
            "price": _hard_stop_val,
            "label": "HARD_STOP",
            "role": {"label": "CATASTROPHIC_STOP", "desc": "Intraday hard stop -- floor - 1.5x hourly ATR"},
            "status": "BREACHED" if (_current_price is not None and _current_price < _hard_stop_val) else "HOLDING",
        })

    # Daily Hard Stop (PA-001 swing-frame catastrophic stop — EMA 21 - 1.5x Daily ATR)
    # [BUGR-001] Match the > 0 guard applied at the output-layer writer (output.py
    # ~1683). daily_hard_stop defaults to 0.0 in data.py and is only populated on
    # Profile A; Profile B runs would otherwise render a DAILY_HARD_STOP hierarchy
    # entry at price 0.00 with status HOLDING (false signal). Spec §4.1.3.
    _daily_hard_stop_val = flat_metrics.get("Daily_Hard_Stop")
    if _daily_hard_stop_val is not None and _daily_hard_stop_val > 0:
        _floor_entries.append({
            "price": _daily_hard_stop_val,
            "label": "DAILY_HARD_STOP",
            "role": {"label": "CATASTROPHIC_STOP", "desc": "Daily hard stop -- EMA 21 - 1.5x Daily ATR (swing-frame last resort)"},
            "status": "BREACHED" if (_current_price is not None and _current_price < _daily_hard_stop_val) else "HOLDING",
        })

    # Psychological Floor (PSY-001 nearest round number below price)
    if _psy_floor is not None:
        _floor_entries.append({
            "price": _psy_floor,
            "label": "PSYCHOLOGICAL",
            "role": {"label": "PSYCHOLOGICAL", "desc": "Nearest round number below current price -- psychological support"},
            "status": "BREACHED" if (_current_price is not None and _current_price < _psy_floor) else "HOLDING",
        })

    # [CNV-001] Annotate floor entries with conviction_tier + conviction_rank
    # BEFORE BRK-active scoping. On the non-BRK path this is the final
    # annotation pass; on the BRK path the retained PSYCHOLOGICAL floor
    # carries its annotation forward (and is re-annotated idempotently at
    # call site 3 alongside the new BRK-specific entries). The BUGR-002
    # partition operates on price and only strips status; conviction fields
    # propagate transparently to overhead_levels.
    _annotate_conviction(_floor_entries)

    # [BUGR-002] Pre-partition sort removed. Post-partition sorts apply
    # per §4.8: _stops_below descending (preserves prior semantic),
    # _overhead ascending (nearest-above-to-price first).

    # ==================================================================
    # BRK-001: STOP HIERARCHY SCOPING (Spec §4.5)
    #
    # When breakout model active, replace the entire pre-breakout floor
    # hierarchy with post-breakout levels only:
    #   - New support (old resistance)
    #   - Tight stop (new support − buffer × ATR)
    #   - Catastrophic stop (new support − 1.5 × ATR)
    #   - Psychological support below price (retained as secondary)
    #
    # Pre-breakout structural levels (SESSION_VWAP, EMA 21, SMA 50, etc.)
    # are excluded from the trade stop hierarchy.  They remain visible in
    # floor_analysis for structural health monitoring.
    # ==================================================================
    if _brk_active:
        _brk_ns_price = flat_metrics.get("BRK_New_Support")
        _brk_ts_price = flat_metrics.get("BRK_Tight_Stop")
        _brk_cs_price = flat_metrics.get("BRK_Catastrophic_Stop")

        _brk_floor_entries = []
        if _brk_ns_price is not None:
            _brk_floor_entries.append({
                "price": _brk_ns_price,
                "label": "NEW_SUPPORT",
                "role": {"label": "BREAKOUT_SUPPORT", "desc": "Old resistance flipped to new support -- breakout thesis anchor"},
                "status": "BREACHED" if (_current_price is not None and _current_price < _brk_ns_price) else "HOLDING",
            })
        if _brk_ts_price is not None:
            _brk_floor_entries.append({
                "price": _brk_ts_price,
                "label": "TIGHT_STOP",
                "role": {"label": "THESIS_STOP", "desc": "New support - ATR buffer -- breakout thesis invalidation level"},
                "status": "BREACHED" if (_current_price is not None and _current_price < _brk_ts_price) else "HOLDING",
            })
        if _brk_cs_price is not None:
            _brk_floor_entries.append({
                "price": _brk_cs_price,
                "label": "CATASTROPHIC_STOP",
                "role": {"label": "CATASTROPHIC_STOP", "desc": "New support - 1.5x ATR -- position sizing, gap protection"},
                "status": "BREACHED" if (_current_price is not None and _current_price < _brk_cs_price) else "HOLDING",
            })
        # Retain psychological floor from original hierarchy
        for _fe in _floor_entries:
            if _fe.get("label") == "PSYCHOLOGICAL":
                _brk_floor_entries.append(_fe)
                break

        _brk_floor_entries.sort(key=lambda x: x["price"], reverse=True)
        # [CNV-001] Annotate BRK floor entries with conviction_tier +
        # conviction_rank. NEW_SUPPORT, TIGHT_STOP, CATASTROPHIC_STOP
        # are first annotated here; the retained PSYCHOLOGICAL entry is
        # re-annotated idempotently (already tagged at call site 2).
        _annotate_conviction(_brk_floor_entries)
        _floor_entries = _brk_floor_entries

    # ==================================================================
    # [BUGR-002] Stop-side partition (Spec §4.1, §4.3, §4.8, §5.1)
    #
    # Partition _floor_entries using current_price predicate:
    #   hierarchy        = entries with price <  current_price (below — "what catches us")
    #   overhead_levels  = entries with price >= current_price (above — informational)
    #
    # Sorts: hierarchy descending (preserved), overhead_levels ascending
    # (nearest-above-first per §4.8).
    #
    # overhead_levels entries drop the `status` field per §4.3 — presence in the
    # container is itself the semantic (all above price by construction).
    #
    # Guard: when _current_price is None (degenerate, should not occur on any
    # real evaluation path) fall back to pre-partition behaviour — keep all
    # entries in hierarchy, emit overhead_levels as null — preserves resilience.
    #
    # BRK-001-active path: the BRK block above replaced _floor_entries with
    # four construction-guaranteed-below-price entries (NEW_SUPPORT, TIGHT_STOP,
    # CATASTROPHIC_STOP, retained PSYCHOLOGICAL). All land in _stops_below;
    # _overhead empty -> null per §4.6. BRK-001 §4.5 scoping preserved.
    # ==================================================================
    if _current_price is not None:
        _stops_below = [
            fe for fe in _floor_entries
            if fe.get("price") is not None and fe["price"] < _current_price
        ]
        _overhead = [
            fe for fe in _floor_entries
            if fe.get("price") is not None and fe["price"] >= _current_price
        ]
    else:
        _stops_below = list(_floor_entries)
        _overhead = []

    _stops_below.sort(key=lambda x: x["price"], reverse=True)
    _overhead.sort(key=lambda x: x["price"])

    # [CFL-001] Annotate floor hierarchy entries with `confluence` on
    # clustered entries (within 0.25x ATR adjacency). Runs POST-partition so
    # only `_stops_below` is scanned — `_overhead` is intentionally excluded
    # per spec §2.2 / §5.3 (overhead_levels confluence deferred to v1.1
    # candidate CFL-001-OBS-1). Runs POST-sort so the greedy adjacent walk
    # operates on sorted prices.
    #
    # Covers BOTH the standard and the BRK-active paths in a single call:
    # on the BRK path, `_floor_entries = _brk_floor_entries` is assigned
    # above (replacing the broad floor hierarchy with the BRK-scoped four-
    # entry list) BEFORE the partition runs, so `_stops_below` is the BRK
    # entry set on that path. This consolidates the spec's §4.2 + §4.3
    # call sites — see CFL-001 hand-back §5.
    _detect_level_confluence(
        _stops_below,
        flat_metrics.get("ATR"),
        _CFL_FLOOR_THRESHOLD_ATR_MULT,
        "floor",
    )

    # ITS-001: Per-field lookback_stale annotation (Spec §4.6 / DQ-1a hybrid).
    # Annotate ESTABLISHED_LOW (10-bar) and AVWAP_10BAR (10-bar) when a global
    # intraday event sits inside the 10-bar lookback. AVWAP_10BAR annotation
    # resolved at Phase 2 entry per §11 audit item 9 (engine emits it as a
    # floor hierarchy entry at transform.py L3241, structurally similar to
    # ESTABLISHED_LOW). Hierarchy entries only; overhead_levels excluded.
    if flat_metrics.get("Intraday_Lookback_Stale") is True:
        for _entry in _stops_below:
            _label = _entry.get("label")
            if _label == "ESTABLISHED_LOW" or _label == "AVWAP_10BAR":
                _entry["lookback_stale"] = True

    # §4.3: strip status field from overhead_levels entries
    for _oh in _overhead:
        _oh.pop("status", None)

    floor_hierarchy = _stops_below if _stops_below else None
    stop_overhead_levels = _overhead if _overhead else None

    # Nest hierarchies inside trade_setup (DQ-9 under target, DQ-10 under stop)
    # [BUGR-002] Target side gains sibling cleared_levels field; stop side gains
    # sibling overhead_levels field. All four nullable per §4.6.
    if trade_setup.get("target") is not None:
        trade_setup["target"]["hierarchy"] = target_hierarchy
        trade_setup["target"]["cleared_levels"] = target_cleared_levels
    elif target_hierarchy or target_cleared_levels:
        trade_setup["target"] = {
            "hierarchy": target_hierarchy,
            "cleared_levels": target_cleared_levels,
        }
    # ==================================================================
    # [DSP-001 / FRR-001-BUG-1 / CEG-002-BUG-1] SOURCE LABEL RE-DERIVE
    #
    # Re-derive trade_setup.target.source.label from the escalation_winner
    # tier when the current source.label conceptually mismatches the winner.
    # Resolves three bug-class siblings sharing the same mechanism:
    #
    #   - DSP-001 (PLTR Profile B C-3): FRR-001 ANALYST_CONSENSUS source label
    #     emitted while DAILY_HIGH wins escalation by price match
    #   - FRR-001-BUG-1 (SNDK-B pattern-1, CRH-B pattern-2): same mechanism,
    #     SNDK-B places winner in cleared_levels (EXCEEDED), CRH-B in hierarchy
    #   - CEG-002-BUG-1 (Profile B non-BRK blue-sky): ATR_PROJECTION (blue sky)
    #     source label emitted while DAILY_HIGH wins by price match
    #
    # Architecture (per spec §3.1): decision-owner authoritative.
    #   - BRK-active paths: compute.py owns the BRK target decision (BRK-001
    #     §8.1 fallback labels per BUGR-006 v2.0 §4.3.3). Skip re-derive —
    #     LABEL-2's "output defers to compute" pattern preserved.
    #   - Non-BRK paths: transform.py hierarchy-escalation owns the "which
    #     tier is the winning price" decision. Re-derive when current
    #     source.label's detected tier differs from escalation_winner tier.
    #
    # Vocabulary preservation (per spec §3.3): the _detect_source_tier helper
    # maps legacy compute/output-layer vocabulary ("10_Bar_Resistance",
    # "WEEKLY_RESISTANCE (price above daily range)", "ANALYST_CONSENSUS",
    # "ATR_PROJECTION (blue sky)") to hierarchy tier vocabulary
    # ("DAILY_HIGH", "WEEKLY_HIGH", "ANALYST_CONSENSUS", "ATR_PROJECTION").
    # Conceptually-matching labels are preserved verbatim (e.g.,
    # "WEEKLY_RESISTANCE (price above daily range)" stays — its detected tier
    # WEEKLY_HIGH matches the winner). Genuinely mismatched labels are
    # overwritten with the winner tier's canonical label.
    #
    # Search scope: BOTH target_hierarchy AND target_cleared_levels per
    # BUGR-002 §4.7 — winners can land in cleared_levels on EXCEEDED paths
    # (SNDK-B pattern-1 case).
    # ==================================================================
    if not _brk_active and trade_setup.get("target") is not None:
        _all_target_entries = (target_hierarchy or []) + (target_cleared_levels or [])
        _winner_entry = next(
            (e for e in _all_target_entries if e.get("escalation_winner")),
            None,
        )
        if _winner_entry is not None:
            _winner_label = _winner_entry.get("label")
            _src = trade_setup["target"].get("source")
            if isinstance(_src, dict):
                _current_label = _src.get("label") or ""
                _detected_tier = _detect_source_tier(_current_label.upper())
                if _detected_tier is not None and _winner_label is not None and _detected_tier != _winner_label:
                    # Genuine mismatch — re-derive from escalation winner.
                    # desc mirrors label per existing transform.py:1259 convention;
                    # richer per-tier descs are TGT-SRC-001 territory (CONCEPT).
                    trade_setup["target"]["source"]["label"] = _winner_label
                    trade_setup["target"]["source"]["desc"] = _winner_label
    if trade_setup.get("stop") is not None:
        trade_setup["stop"]["hierarchy"] = floor_hierarchy
        trade_setup["stop"]["overhead_levels"] = stop_overhead_levels
    elif floor_hierarchy or stop_overhead_levels:
        trade_setup["stop"] = {
            "hierarchy": floor_hierarchy,
            "overhead_levels": stop_overhead_levels,
        }

    # --- REC-001 Phase 2D: recovery_analysis group (Spec §8.3) ---
    _rec_status = flat_metrics.get("Recovery_Status", "NOT EVALUATED")
    if _rec_status == "NOT EVALUATED":
        recovery_analysis = {"recovery_status": "NOT EVALUATED"}
    else:
        recovery_analysis = {
            "recovery_status":             flat_metrics.get("Recovery_Status"),
            "base_bar_count":              flat_metrics.get("Recovery_Base_Bar_Count"),
            "swing_low_price":             flat_metrics.get("Recovery_Swing_Low_Price"),
            "swing_low_bar_index":         flat_metrics.get("Recovery_Swing_Low_Bar_Index"),
            "ema_cross_bar_index":         flat_metrics.get("Recovery_EMA_Cross_Bar_Index"),
            "di_spread_current":           flat_metrics.get("Recovery_DI_Spread_Current"),
            "di_spread_at_swing_low":      flat_metrics.get("Recovery_DI_Spread_At_Swing_Low"),
            "atr_contraction_ratio":       flat_metrics.get("Recovery_ATR_Contraction_Ratio"),
            "retest_confirmed":            flat_metrics.get("Recovery_Retest_Confirmed"),
            "time_stop_bars_remaining":    flat_metrics.get("Recovery_Time_Stop_Bars_Remaining"),
            "recovery_target":             flat_metrics.get("Recovery_Target"),
            "recovery_target_source":      flat_metrics.get("Recovery_Target_Source"),
            "recovery_active_count":       flat_metrics.get("Recovery_Active_Count", 0),
            "recovery_capital_rr":         flat_metrics.get("Recovery_Capital_RR"),
            "crg_bypass_context":          flat_metrics.get("Recovery_CRG_Bypass_Context"),
            "diagnostic":                  flat_metrics.get("Recovery_Diagnostic"),
        }

    # --- SBO-001 Phase 2: swing_breakout_confirmation group (Spec §8.3) ---
    _sbo_age = flat_metrics.get("SBO_Breakout_Bar_Age")
    _sbo_trending = flat_metrics.get("SBO_Trending_Reached")
    _sbo_timeout = flat_metrics.get("SBO_Confirmation_Timeout")
    _sbo_rvol = flat_metrics.get("SBO_RVOL")

    if _sbo_age is not None:
        # Derive status label
        if _sbo_trending:
            _sbc_status_label = "CONFIRMED"
            _sbc_status_desc = "Breakout converted -- TRENDING state reached"
        elif _sbo_timeout:
            _sbc_status_label = "EXPIRED"
            _sbc_status_desc = "Breakout failed to convert -- TRENDING not reached within confirmation window"
        else:
            _sbc_status_label = "PENDING"
            _sbc_status_desc = "Awaiting trend confirmation -- monitoring active"

        _sbc_remaining = max(0, SBO_CONFIRMATION_BARS - _sbo_age)

        # [SBC-001] Compute breakout_rvol band before emission for clean shape
        _sbc_rvol_cond, _sbc_rvol_thr = _breakout_rvol_band(_sbo_rvol)

        swing_breakout_confirmation = {
            "status": {
                "label": _sbc_status_label,
                "desc": _sbc_status_desc,
            },
            "breakout_age": {
                "value": _sbo_age,
                "unit": "bars",
                "timeframe": "hour",
                "desc": "Bars elapsed since breakout event",
            },
            "confirmation_window": {
                "remaining": _sbc_remaining,
                "max": SBO_CONFIRMATION_BARS,
                "unit": "bars",
                "desc": "Bars allowed to reach TRENDING before forced exit",
            },
            "breakout_rvol": {
                "value": _sbo_rvol,
                "condition": _sbc_rvol_cond,
                "thresholds": _sbc_rvol_thr,
                "desc": "Relative volume on breakout bar (volume / 20-bar avg)",
            },
        }
    else:
        swing_breakout_confirmation = None

    # ==================================================================
    # BRK-001-GAP-2: Thesis invalidation annotation (DQ-2: Option B explicit).
    #
    # Option A resolution (Operator-confirmed): when the thesis fails but
    # SBO is inactive (Profile B, ETFs — SBO only runs on Profile A non-ETF),
    # build a minimal swing_breakout_confirmation container to hold the
    # breakout_thesis sub-object. This preserves DQ-2's grouped-annotation
    # contract across ALL profiles (TC-GAP2-04).
    #
    # Contract note: downstream consumers of swing_breakout_confirmation
    # must null-check SBO fields (status/breakout_age/confirmation_window/
    # breakout_rvol) as they will be absent when the section exists only
    # to carry the thesis annotation.
    # ==================================================================
    _thesis_status = flat_metrics.get("Breakout_Thesis_Status")
    if _thesis_status == "FAILED":
        _thesis_ns = flat_metrics.get("BRK_Thesis_New_Support")
        _thesis_close = flat_metrics.get("BRK_Thesis_Bar_Close")
        _thesis_delta = flat_metrics.get("BRK_Thesis_Delta")
        _thesis_sub = {
            "status": {
                "label": "FAILED",
                "desc": "Breakout thesis invalidated -- price closed below new support level. Standard pullback evaluation applied.",
            },
            "new_support": _thesis_ns,
            "bar_close": _thesis_close,
            "delta": _thesis_delta,
        }
        if swing_breakout_confirmation is None:
            # Option A: minimal container — SBO inactive (Profile B, ETFs)
            swing_breakout_confirmation = {"breakout_thesis": _thesis_sub}
        else:
            # SBO active — attach thesis annotation alongside SBO fields
            swing_breakout_confirmation["breakout_thesis"] = _thesis_sub

    # ==================================================================
    # SFR-001: Signal Freshness annotation into action_summary
    # Maps Signal_Freshness from flat_metrics into action_summary with
    # self-doc {label, desc} structure. VALID and RECOVERY CANDIDATE only
    # (output.py only writes the key on those paths).
    # ==================================================================
    _sfr_label = flat_metrics.get("Signal_Freshness")
    if _sfr_label:
        _sfr_note = flat_metrics.get("Signal_Freshness_Note")
        action_summary["signal_freshness"] = {
            "label": _sfr_label,
            "desc": _sfr_note if _sfr_note else {
                "ARRIVAL": "First qualifying bar -- new entry opportunity",
                "CONTINUATION": "Signal persists from prior bar",
                "RE-ENTRY": "Signal re-qualified after brief lapse",
                "PENDING_VWAP": "Freshness clock deferred -- awaiting VWAP trigger confirmation",
            }.get(_sfr_label, ""),
        }

    # AVWAP-001 T8: Surface VWAP trigger status in action_summary (VALID/RECOVERY paths)
    _as_verdict = action_summary.get("verdict")
    if _as_verdict in ("VALID", "RECOVERY CANDIDATE"):
        _vwap_status = flat_metrics.get("VWAP_Trigger_Status")
        if _vwap_status is not None:
            _entry_strat = action_summary.get("entry_strategy", {})
            if isinstance(_entry_strat, dict):
                _entry_strat["vwap_trigger"] = {
                    "status": _vwap_status,
                    "price": flat_metrics.get("VWAP_Trigger_Price"),
                    "confirmed": flat_metrics.get("VWAP_Trigger_Confirmed"),
                    "note": flat_metrics.get("VWAP_Trigger_Note"),
                    "desc": "Session VWAP reclaim condition (Profile A intraday timing filter)",
                }

    # ==================================================================
    # CQS-001: Consolidation Quality Score mapping into action_summary
    # Post-verdict annotation — VALID breakout paths only
    # (SWING_BREAKOUT, BREAKOUT). Maps CQS flat keys into self-doc
    # {score, label, desc} structure with component breakdown and
    # diagnostics. Adds caution_factors when label is LOW.
    # ==================================================================
    _cqs_composite = flat_metrics.get("CQS_Composite_Score")
    if _cqs_composite is not None:
        _cqs_label = flat_metrics.get("CQS_Composite_Label", "LOW")
        _cqs_label_descs = {
            "HIGH": "Strong consolidation quality: tight range, declining volume, and progressive pullback shallowing.",
            "MODERATE": "Partial consolidation quality: some contraction signals present but incomplete pattern.",
            "LOW": "Weak consolidation quality: limited contraction evidence. Exercise additional discretion.",
        }
        _cqs_rc = flat_metrics.get("CQS_Range_Contraction_Score")
        _cqs_vc = flat_metrics.get("CQS_Volume_Contraction_Score")
        _cqs_vcp = flat_metrics.get("CQS_VCP_Score")

        def _cqs_component_label(s):
            if s is None:
                return None
            if s >= 70:
                return "HIGH"
            if s >= 40:
                return "MODERATE"
            return "LOW"

        action_summary["consolidation_quality"] = {
            "composite": {
                "score": _cqs_composite,
                "label": _cqs_label,
                "desc": _cqs_label_descs.get(_cqs_label, ""),
            },
            "components": {
                "range_contraction": {
                    "score": _cqs_rc,
                    "label": _cqs_component_label(_cqs_rc),
                    "desc": "Early vs late half average bar range comparison (weight: 40%)",
                },
                "volume_contraction": {
                    "score": _cqs_vc,
                    "label": _cqs_component_label(_cqs_vc),
                    "desc": "Volume trend slope + terminal volume ratio (weight: 35%)",
                },
                "vcp_proxy": {
                    "score": _cqs_vcp,
                    "label": _cqs_component_label(_cqs_vcp),
                    "desc": "Pullback depth shallowing (VCP signature) (weight: 25%)",
                },
            },
            "diagnostics": {
                "atr_gate_passed": flat_metrics.get("CQS_ATR_Gate_Passed"),
                "atr_ratio": flat_metrics.get("CQS_ATR_Ratio"),
                "swing_lows_found": flat_metrics.get("CQS_VCP_Swing_Lows_Found"),
                "volume_terminal_ratio": flat_metrics.get("CQS_Volume_Terminal_Ratio"),
            },
        }

        # CAUTION factor: append when label is LOW (Spec §4.6)
        _cqs_caution = flat_metrics.get("CQS_Caution_Note")
        if _cqs_caution:
            if "caution_factors" not in action_summary:
                action_summary["caution_factors"] = []
            action_summary["caution_factors"].append({
                "factor": "CQS_LOW_QUALITY",
                "desc": _cqs_caution,
            })

    # ==================================================================
    # IVR-001: Volatility Regime Context section
    # Spec: IVR001_Volatility_Regime_Context_Spec_v1_0 §6
    # ==================================================================
    _ivr_iv = flat_metrics.get("IV_Current")
    _ivr_hv = flat_metrics.get("HV_30D")
    _ivr_ratio = flat_metrics.get("IV_HV_Ratio")
    _ivr_regime = flat_metrics.get("Volatility_Regime")
    _ivr_regime_desc = flat_metrics.get("Volatility_Regime_Desc", "")
    _ivr_interp = flat_metrics.get("Volatility_Interpretation")
    _ivr_interp_desc = flat_metrics.get("Volatility_Interpretation_Desc", "")
    _ivr_caution = flat_metrics.get("Volatility_Caution_Factor")

    volatility_regime = {
        "iv": {
            "value": _ivr_iv,
            "unit": "percent_annualised",
            "desc": "Current implied volatility (IBKR model-implied, 30-day forward)",
        },
        "hv": {
            "value": _ivr_hv,
            "unit": "percent_annualised",
            "desc": "30-day historical volatility (daily log returns, annualised)",
        },
        "ratio": {
            "value": _ivr_ratio,
            "desc": "IV / HV ratio. Above 1.0 = options market expects more movement than realised. Below 1.0 = options expect less.",
        },
        "regime": {
            "label": _ivr_regime,
            "desc": _ivr_regime_desc,
        },
        "thresholds": {
            "complacent": {"value": 0.8, "desc": "Below this: options market underpricing risk. Occurs ~15% of the time historically."},
            "elevated": {"value": 1.2, "desc": "Above this: options market pricing moderately more risk. Accounts for normal 2-4 point VRP on most stocks."},
            "extreme": {"value": 1.5, "desc": "Above this: significant divergence. Strong signal regardless of context."},
        },
        "context_interpretation": {
            "engine_state": flat_metrics.get("Engine_State"),
            "trigger": flat_metrics.get("Trigger"),
            "interpretation": {
                "label": _ivr_interp,
                "desc": _ivr_interp_desc,
            },
        },
        "caution_factor": _ivr_caution,
    }

    # IVR-001: action_summary.volatility_regime (omit if UNAVAILABLE)
    if _ivr_regime and _ivr_regime != "UNAVAILABLE":
        action_summary["volatility_regime"] = {
            "label": _ivr_regime,
            "interpretation": _ivr_interp,
        }

        # Append caution factor when ELEVATED or EXTREME (Spec §6.2)
        if _ivr_caution:
            if "caution_factors" not in action_summary:
                action_summary["caution_factors"] = []
            action_summary["caution_factors"].append({
                "factor": "VOLATILITY_REGIME",
                "desc": _ivr_caution,
            })

    # RLY-001: Rally state grouped sub-object (Spec §3.2 / §4.3). Fresh dict
    # built from the 8 RLY flat keys; structurally independent from any
    # partitioned hierarchy. Returns None on defensive-null paths.
    rally_state = _assemble_rally_state_group(flat_metrics)

    # --- Final result dict ---
    result = {
        "data_basis":           flat_metrics.get("Data_Basis", None),
        "action_summary":       action_summary,
        "trade_snapshot":       trade_snapshot,
        "trade_quality":        _tq,
        "trade_risk":           trade_risk,
        "trend_state":          trend_state,
        "floor_analysis":       floor_analysis,
        "trade_setup":          trade_setup,
        "extension_analysis":   extension_analysis,
        "psychological_levels": psychological_levels,
        "volatility_regime":    volatility_regime,
        "rally_state":          rally_state,
        "entry_proximity":      entry_proximity,
        "exit_signals":         exit_signals,
        "recovery_analysis":    recovery_analysis,
    }
    # SBO-001: Only include when active (Profile A non-ETF with breakout detected)
    if swing_breakout_confirmation is not None:
        result["swing_breakout_confirmation"] = swing_breakout_confirmation

    # ITS-001: Intraday-Tactical Surface top-level group (Spec §2.2 / DQ-1b).
    # Reads the sentinel-key block stashed in flat_metrics by output.py
    # `_assemble_intraday_tactical` (Spec §5.2 storage-mechanism pattern).
    # Block is None on Profile B/C and Profile A defensive paths — group
    # structurally absent in those cases (WKC-001 macro_frame precedent).
    # Slots after swing_breakout_confirmation, before _debug.
    _its_block = flat_metrics.get("_intraday_tactical_block")
    if _its_block is not None:
        result["intraday_tactical"] = _its_block
    flat_metrics.pop("_intraday_tactical_block", None)

    if debug:
        result["_debug"] = _map(_GROUP_DEBUG)
    return result


def _error_output(verdict: str, reason: str, flat_metrics: dict = None,
                  debug: bool = False) -> dict:
    """Build output for error and data-layer early-return paths.

    DIAG-001 Phase 2B (DD-9):
    ERROR verdict: action_summary ONLY — all other groups suppressed.
    INVALID verdict (data-layer HALTs): full grouped output with action_summary.
    """
    action_summary = {
        "verdict": verdict,
        "reason": {"label": reason, "detail": None},
        "exit_status": {"active": False, "reason": None},
    }
    if verdict == "INVALID":
        action_summary["approaching"] = False

    if verdict == "ERROR":
        # DD-9: ERROR path emits action_summary only
        result = {"action_summary": action_summary}
        if debug:
            result["_debug"] = None
        return result
    else:
        # INVALID from data layer — full grouped output
        return _transform_output(action_summary, flat_metrics or {}, debug=debug)


# ---------------------------------------------------------------------------
# _flatten — development utility for backward compatibility
# ---------------------------------------------------------------------------

_HIGHER_FRAME_REVERSE_A = {
    "golden_cross": "Context_Golden_Cross", "price_vs_sma200": "Context_Price_vs_SMA200",
    "sma200": "Context_SMA200", "daily_sma50": "Context_Daily_SMA50",
    "daily_sma50_slope": "Context_Daily_SMA50_Slope",
}
_HIGHER_FRAME_REVERSE_B = {
    "golden_cross": "Context_Weekly_Golden_Cross", "price_vs_sma200": "Context_Weekly_Price_vs_SMA200",
    "sma50": "Context_Weekly_SMA50", "sma50_slope": "Context_Weekly_SMA50_Slope",
    "sma50_rising": "Context_Weekly_SMA50_Rising",
}
_HIGHER_FRAME_REVERSE_C = {
    "golden_cross": "Context_Monthly_Golden_Cross", "price_vs_sma200": "Context_Monthly_Price_vs_SMA200",
    "sma200": "Context_Monthly_SMA200", "sma50": "Context_Monthly_SMA50",
    "sma50_slope": "Context_Monthly_SMA50_Slope",
}


def _flatten(grouped: dict) -> tuple:
    """Convert grouped output back to (status, diagnostic, metrics) tuple.

    SelfDoc Batch 2: Handles new structures from all 7 items.
    AS-001: reason is {label, detail}. mandate replaces action. exit_status replaces existing_position_exit_*.
    """
    _as = grouped.get("action_summary", {})
    verdict = _as.get("verdict", "ERROR")

    # Map verdict back to legacy status for backward compat
    if verdict == "VALID":
        status = "PASS"
    elif verdict == "INVALID":
        status = "HALT"
    elif verdict == "WAIT":
        status = "HALT"  # THS-001: WAIT is a blocking verdict like INVALID
    elif verdict == "RECOVERY CANDIDATE":
        status = "PASS"  # REC-001 Phase 2D: recovery candidate is actionable
    else:
        status = "ERROR"

    # AS-001: Reconstruct diagnostic from new reason structure
    _reason_obj = _as.get("reason", {})
    if isinstance(_reason_obj, dict):
        _reason = _reason_obj.get("label", "")
        _detail = _reason_obj.get("detail", "") or ""
    else:
        _reason = str(_reason_obj) if _reason_obj else ""
        _detail = ""
    _mandate = _as.get("mandate", "") or _as.get("action", "") or ""
    diagnostic = f"{_reason}. {_detail} {_mandate}".strip()

    flat = {}

    # PE-42: Reverse-map data_basis from top level
    _db = grouped.get("data_basis")
    if _db is not None:
        flat["Data_Basis"] = _db

    def _unmap(data, table):
        for fk, gk in table:
            if gk in data:
                flat[fk] = data[gk]

    def _unmap_subgrouped(data, subgroups, scalars=None):
        for sg_name, sg_table in subgroups:
            sg = data.get(sg_name, {})
            if sg:
                _unmap(sg, sg_table)
        if scalars:
            _unmap(data, scalars)

    # --- SNAP-001: trade_snapshot extraction ---
    _ts = grouped.get("trade_snapshot", {})
    if _ts:
        _price_obj = _ts.get("price", {})
        if isinstance(_price_obj, dict):
            flat["Price"] = _price_obj.get("current")
            flat["Bar_Close_Price"] = _price_obj.get("bar_close")
            _src = _price_obj.get("source", {})
            flat["Price_Source"] = _src.get("label") if isinstance(_src, dict) else _src
        else:
            flat["Price"] = _ts.get("current_price")
            flat["Bar_Close_Price"] = _ts.get("bar_close_price")
            flat["Price_Source"] = _ts.get("price_source")

        _sf = _ts.get("structural_floor", {})
        flat["Structural_Floor"] = _sf.get("price") if isinstance(_sf, dict) else _sf

        _res = _ts.get("resistance", {})
        flat["Resistance"] = _res.get("price") if isinstance(_res, dict) else _res

        flat["Support_Resistance_Note"] = _ts.get("support_resistance_note")  # BUG-R1

        _atr_obj = _ts.get("atr", {})
        flat["ATR"] = _atr_obj.get("value") if isinstance(_atr_obj, dict) else None

        _adv_obj = _ts.get("avg_daily_volume", {})
        flat["ADV_20"] = _adv_obj.get("value") if isinstance(_adv_obj, dict) else _adv_obj

        # classification
        cls = _ts.get("classification", {})
        if cls:
            type_val = cls.get("type")
            if type_val is not None:
                flat["Is_ETF"] = (type_val == "ETF")
            _cvx = cls.get("convexity", {})
            flat["Convexity_Class"] = _cvx.get("label") if isinstance(_cvx, dict) else _cvx
            flat["ETF_Primary_Exchange"] = cls.get("exchange")
            _etf_d = cls.get("etf_detection", {})
            flat["ETF_Detection_Source"] = _etf_d.get("label") if isinstance(_etf_d, dict) else _etf_d

        # SNAP-001: price_levels extraction
        _pl = _ts.get("price_levels", {})
        if _pl:
            for _pk, _fk in [("ema_8", "EMA_8"), ("ema_21", "EMA_21"), ("sma_50", "SMA_50"), ("sma_200", "SMA_200"), ("vwap", "VWAP")]:
                _pv = _pl.get(_pk, {})
                flat[_fk] = _pv.get("price") if isinstance(_pv, dict) else _pv

    # --- trade_quality: custom extraction for trend_health (THS-002) + volume (VOL-003) ---
    _tq = grouped.get("trade_quality", {})
    th = _tq.get("trend_health", {}) if _tq else {}
    if th:
        _score = th.get("score", {})
        flat["Trend_Health_Score"] = _score.get("value") if isinstance(_score, dict) else _score
        flat["THS_Label"] = _score.get("label") if isinstance(_score, dict) else None
        for sub_key, flat_key in [
            ("floor_buffer", "THS_Floor_Buffer"),
            ("dir_momentum", "THS_Dir_Momentum"),
            ("trend_age", "THS_Trend_Age"),
            ("structure", "THS_Structure"),
        ]:
            sub = th.get(sub_key, {})
            flat[flat_key] = sub.get("value") if isinstance(sub, dict) else sub

        # STRUCT-001-TFR-1: advisory extraction
        _adv = th.get("advisory", {})
        if _adv:
            _dc = _adv.get("death_cross_cap", {})
            flat["THS_Death_Cross_Cap"] = _dc.get("active", False) if isinstance(_dc, dict) else False
            _cc = _adv.get("component_cap", {})
            flat["THS_Component_Cap"] = _cc.get("trigger") if isinstance(_cc, dict) else None
            _vp = _adv.get("vwap_penalty", {})
            flat["THS_VWAP_Floor_Penalty"] = _vp.get("active", False) if isinstance(_vp, dict) else False
            flat["THS_VWAP_Floor_Note"] = _vp.get("note") if isinstance(_vp, dict) else None
            _cw = _adv.get("context_warning", {})
            flat["THS_Context_Advisory"] = _cw.get("message") if isinstance(_cw, dict) else None

    # VOL-003: volume extraction
    vol = _tq.get("volume", {}) if _tq else {}
    if vol:
        _cr = vol.get("confirmation_ratio", {})
        if isinstance(_cr, dict):
            flat["Vol_Confirm_Ratio"] = _cr.get("value")
            flat["Vol_Confirm_State"] = _cr.get("label")
        _summary = vol.get("summary", {})
        if isinstance(_summary, dict):
            flat["Volume_Context_Label"] = _summary.get("label")
        _poc = vol.get("poc", {})
        if isinstance(_poc, dict):
            flat["Vol_PoC_Price"] = _poc.get("price")
            _pd = _poc.get("distance_atr", {})
            flat["Vol_PoC_Distance_ATR"] = _pd.get("value") if isinstance(_pd, dict) else _pd
            flat["Vol_PoC_Position"] = _poc.get("position")
        _avwap = vol.get("avwap", {})
        if isinstance(_avwap, dict):
            flat["AVWAP_Price"] = _avwap.get("price")
            flat["AVWAP_Position"] = _avwap.get("position")
        _adddv = vol.get("avg_daily_dollar_volume", {})
        if isinstance(_adddv, dict):
            flat["ADV_20_Dollar"] = _adddv.get("value")

        # VOL-004: bar_volume + session_volume
        _bv = vol.get("bar_volume", {})
        if isinstance(_bv, dict):
            flat["Bar_Volume"] = _bv.get("value")
        _sv = vol.get("session_volume", {})
        if isinstance(_sv, dict):
            flat["Session_Volume"] = _sv.get("value")

    # EXT-001: overextension_exception backward compat
    ext = grouped.get("extension_analysis", {})
    if ext:
        _override = ext.get("override", {})
        if isinstance(_override, dict):
            # GR-6: resolve to scalar — None if not eligible, reason string if eligible
            if _override.get("eligible"):
                flat["Trend_Quality_Override"] = _override.get("reason") or _override.get("note") or "OVERRIDE"
            else:
                flat["Trend_Quality_Override"] = None

    # --- trade_risk: custom extraction (RISK-001 / RISK-UX-001) ---
    tr = grouped.get("trade_risk", {})
    if tr:
        _summary = tr.get("summary", {})
        if isinstance(_summary, dict):
            flat["Risk_Summary_Label"] = _summary.get("label")
            flat["Risk_Summary_Desc"] = _summary.get("desc")
            _rpu_obj = _summary.get("risk_per_unit", {})
            if isinstance(_rpu_obj, dict):
                flat["Risk_Per_Unit"] = _rpu_obj.get("value")
            else:
                flat["Risk_Per_Unit"] = None
        prr = tr.get("price_reward_risk", {})
        if isinstance(prr, dict):
            flat["Reward_Risk"] = prr.get("value")
            flat["Reward_Risk_Note"] = prr.get("note")
            _thr = prr.get("threshold", {})
            if isinstance(_thr, dict):
                flat["Expectancy_Threshold"] = _thr.get("value")
                flat["Expectancy_Threshold_Note"] = _thr.get("note")
        crr = tr.get("capital_reward_risk", {})
        if isinstance(crr, dict):
            flat["Capital_Reward_Risk"] = crr.get("value")
            _st = crr.get("status", {})
            if isinstance(_st, dict):
                flat["Capital_RR_Label"] = _st.get("label")
        # RISK-UX-001: fundamental_reward_risk (was fundamental_rr)
        _frr = tr.get("fundamental_reward_risk", {})
        if isinstance(_frr, dict):
            flat["Fundamental_RR"] = _frr.get("value")
            flat["Fundamental_RR_Label"] = _frr.get("label")
            flat["Fundamental_RR_Note"] = _frr.get("advisory")
            _al = _frr.get("analyst_levels", {})
            if isinstance(_al, dict):
                flat["Fundamental_Target"] = _al.get("target")
                flat["Fundamental_Floor"] = _al.get("floor")
                flat["Fundamental_Target_High"] = _al.get("ceiling")
                flat["Fundamental_Analyst_Count"] = _al.get("coverage")

        # PA-001 Phase 2: capital_rr_role reverse mapping
        _crr_role = tr.get("capital_rr_role", {})
        if isinstance(_crr_role, dict):
            flat["Capital_RR_Role"] = _crr_role.get("label")
            flat["Capital_RR_Role_Desc"] = _crr_role.get("desc")

    # --- trend_state: custom extraction (TS-001) ---
    ts = grouped.get("trend_state", {})
    if ts:
        clf = ts.get("classification", {})
        if clf:
            _st_obj = clf.get("state", {})
            flat["Engine_State"] = _st_obj.get("label") if isinstance(_st_obj, dict) else _st_obj
            _ab = clf.get("age_bars", {})
            flat["Trend_Age_Bars"] = _ab.get("value") if isinstance(_ab, dict) else _ab
            _mods = clf.get("modifiers", {})
            _mods_active = _mods.get("active", []) if isinstance(_mods, dict) else []
            if _mods_active:
                flat["Active_Modifiers"] = ", ".join(
                    f"{m.get('label', '')} ({m.get('name', '')})" if isinstance(m, dict)
                    else str(m) for m in _mods_active
                )
            else:
                flat["Active_Modifiers"] = "None"
            _ch = clf.get("churn", {})
            if isinstance(_ch, dict):
                _ch_label = _ch.get("label", "CLEAR")
                if _ch_label == "ACTIVE":
                    flat["Inst_Churn"] = "ACTIVE (Inst. Churn)"
                elif _ch_label == "INFORMATIONAL":
                    flat["Inst_Churn"] = "INFORMATIONAL (Inst. Churn -- C-3: no action mandated)"
                else:
                    flat["Inst_Churn"] = "CLEAR (No Churn)"
            else:
                flat["Inst_Churn"] = _ch
        dr = ts.get("directional", {})
        if dr:
            _adx_obj = dr.get("adx", {})
            flat["ADX"] = _adx_obj.get("value") if isinstance(_adx_obj, dict) else _adx_obj
            _acc = dr.get("accel", {})
            if isinstance(_acc, dict):
                _rate = _acc.get("rate", {})
                flat["ADX_Accel"] = _rate.get("value") if isinstance(_rate, dict) else _rate
                _acc_st = _acc.get("state", {})
                flat["ADX_Accel_State"] = _acc_st.get("label") if isinstance(_acc_st, dict) else _acc_st
            _di = dr.get("di", {})
            if isinstance(_di, dict):
                flat["DI_Plus"] = _di.get("plus")
                flat["DI_Minus"] = _di.get("minus")

    # --- FA-001: floor_analysis extraction ---
    fa = grouped.get("floor_analysis", {})
    if fa:
        _anchor = fa.get("anchor", {})
        if isinstance(_anchor, dict):
            flat["Anchor_Label"] = _anchor.get("desc")
            flat["Anchor_Type"] = _anchor.get("type")
            flat["Structural_Floor"] = _anchor.get("price") or flat.get("Structural_Floor")
        _ff = fa.get("floor_failure", {})
        if isinstance(_ff, dict):
            _ffs = _ff.get("status", {})
            flat["Floor_Failure_Status_Label"] = _ffs.get("label") if isinstance(_ffs, dict) else None
            _ffc = _ff.get("context", {})
            flat["Floor_Failure_Context"] = _ffc.get("label") if isinstance(_ffc, dict) else _ffc
            _bd = _ff.get("breach_distance", {})
            flat["Floor_Breach_Dist"] = _bd.get("value") if isinstance(_bd, dict) else _bd
            _rp = _ff.get("reclaim_progress", {})
            flat["Floor_Failure_Reclaim"] = _rp.get("value") if isinstance(_rp, dict) else _rp
            _thr = _ff.get("threshold", {})
            flat["Floor_Failure_Threshold"] = _thr.get("value") if isinstance(_thr, dict) else _thr
        _fp = fa.get("floor_proximity_pct", {})
        if isinstance(_fp, dict):
            flat["Floor_Prox_Pct"] = _fp.get("value")

        # higher_frame extraction
        hf = fa.get("higher_frame", {})
        if hf and isinstance(hf, dict):
            _tf = hf.get("timeframe", {})
            _tf_label = _tf.get("label") if isinstance(_tf, dict) else None
            _gc = hf.get("golden_cross", {})
            _s50 = hf.get("sma50", {})
            _s200 = hf.get("sma200", {})
            # [WKC-002] Stage classification extraction (same shape across all 3 timeframes)
            _hf_ms = hf.get("market_stage", {})
            _hf_ms_stage_label = None
            if isinstance(_hf_ms, dict):
                _hf_ms_stage = _hf_ms.get("stage")
                if isinstance(_hf_ms_stage, dict):
                    _hf_ms_stage_label = _hf_ms_stage.get("label")
            if _tf_label == "DAILY":
                if isinstance(_gc, dict): flat["Context_Golden_Cross"] = _gc.get("value")
                if isinstance(_s200, dict):
                    flat["Context_SMA200"] = _s200.get("price")
                    _pd200 = _s200.get("price_distance", {})
                    flat["Context_Price_vs_SMA200"] = _pd200.get("value") if isinstance(_pd200, dict) else None
                if isinstance(_s50, dict):
                    flat["Context_Daily_SMA50"] = _s50.get("price")
                    _sl = _s50.get("slope", {})
                    flat["Context_Daily_SMA50_Slope"] = _sl.get("value") if isinstance(_sl, dict) else None
                if _hf_ms_stage_label is not None:
                    flat["Context_Daily_Stage_Classification"] = _hf_ms_stage_label   # [WKC-002]
                # [UX-002] Re-home Daily_ATR + Daily_Protective_Anchor reverse-map
                # entries (spec §4.3b). Daily_ATR <- higher_frame.daily_atr.value
                # (Profile-A sub-object added by Change 1). Daily_Protective_Anchor
                # <- higher_frame.ema.ema_21 (numerically equal per DQ-4; both
                # reduce to round(df_ctx['EMA_21'].iloc[-1] / price_scaler, 2)).
                _hf_datr = hf.get("daily_atr")
                if isinstance(_hf_datr, dict):
                    flat["Daily_ATR"] = _hf_datr.get("value")
                _hf_ema = hf.get("ema")
                if isinstance(_hf_ema, dict):
                    _hf_ema21 = _hf_ema.get("ema_21")
                    if _hf_ema21 is not None:
                        flat["Daily_Protective_Anchor"] = _hf_ema21
            elif _tf_label == "WEEKLY":
                if isinstance(_gc, dict): flat["Context_Weekly_Golden_Cross"] = _gc.get("value")
                if isinstance(_s50, dict):
                    flat["Context_Weekly_SMA50"] = _s50.get("price")
                    _sl = _s50.get("slope", {})
                    flat["Context_Weekly_SMA50_Slope"] = _sl.get("value") if isinstance(_sl, dict) else None
                # [WKC-002] Profile B Weekly SMA 200 absolute value
                if isinstance(_s200, dict):
                    flat["Context_Weekly_SMA200"] = _s200.get("price")
                    _pd200 = _s200.get("price_distance", {})
                    flat["Context_Weekly_Price_vs_SMA200"] = _pd200.get("value") if isinstance(_pd200, dict) else None
                if _hf_ms_stage_label is not None:
                    flat["Context_Weekly_Stage_Classification"] = _hf_ms_stage_label   # [WKC-002]
            elif _tf_label == "MONTHLY":
                if isinstance(_gc, dict): flat["Context_Monthly_Golden_Cross"] = _gc.get("value")
                if isinstance(_s50, dict):
                    flat["Context_Monthly_SMA50"] = _s50.get("price")
                    _sl = _s50.get("slope", {})
                    flat["Context_Monthly_SMA50_Slope"] = _sl.get("value") if isinstance(_sl, dict) else None
                if isinstance(_s200, dict):
                    flat["Context_Monthly_SMA200"] = _s200.get("price")
                    _pd200 = _s200.get("price_distance", {})
                    flat["Context_Monthly_Price_vs_SMA200"] = _pd200.get("value") if isinstance(_pd200, dict) else None
                if _hf_ms_stage_label is not None:
                    flat["Context_Monthly_Stage_Classification"] = _hf_ms_stage_label   # [WKC-002]

            # [EMA50-001 OD-2] higher_frame.ema_50 reverse-map -- closes Phase 3
            # OD-2 symmetry gap. Parallel to the sma50 timeframe-keyed reverse-map
            # above; richer per DQ-10 (writes canonical Context_EMA_50 +
            # Context_EMA_50_Slope + Context_EMA_50_Slope_Bias in addition to the
            # timeframe-specific keys, mirroring output.py:846-863's canonical
            # derivation).
            _e50 = hf.get("ema_50")
            if isinstance(_e50, dict):
                _e50_price = _e50.get("price")
                _e50_slope_obj = _e50.get("slope")
                if isinstance(_e50_slope_obj, dict):
                    _e50_slope_val = _e50_slope_obj.get("value")
                    _e50_bias_obj = _e50_slope_obj.get("bias")
                    _e50_bias_label = _e50_bias_obj.get("label") if isinstance(_e50_bias_obj, dict) else None
                else:
                    _e50_slope_val = None
                    _e50_bias_label = None
                # Timeframe-specific flat keys (parallel to SMA 50 pattern above)
                if _tf_label == "DAILY":
                    flat["Context_Daily_EMA_50"] = _e50_price
                    flat["Context_Daily_EMA_50_Slope"] = _e50_slope_val
                elif _tf_label == "WEEKLY":
                    flat["Context_Weekly_EMA_50"] = _e50_price
                    flat["Context_Weekly_EMA_50_Slope"] = _e50_slope_val
                elif _tf_label == "MONTHLY":
                    flat["Context_Monthly_EMA_50"] = _e50_price
                    flat["Context_Monthly_EMA_50_Slope"] = _e50_slope_val
                # Canonical aggregated keys (DQ-10 deliberate enhancement;
                # SMA 50 reverse-map does not produce canonical equivalents).
                flat["Context_EMA_50"] = _e50_price
                flat["Context_EMA_50_Slope"] = _e50_slope_val
                if _e50_bias_label is not None:
                    flat["Context_EMA_50_Slope_Bias"] = _e50_bias_label

        # [WKC-001 v1.1] macro_frame reverse-map -- proactive guard against
        # EMA50-001-OD-2 regression class. Round-trips all 14 Context_Macro_*
        # flat keys cleanly (13 from v1.0 + Context_Macro_Stage_Classification
        # added in v1.1). Profile A only; macro_frame is None on B/C so
        # the isinstance(mf, dict) guard short-circuits.
        mf = fa.get("macro_frame")
        if isinstance(mf, dict):
            _m_sma50 = mf.get("sma50")
            if isinstance(_m_sma50, dict):
                flat["Context_Macro_SMA_50"] = _m_sma50.get("price")
                _m_sma50_slope = _m_sma50.get("slope")
                flat["Context_Macro_SMA_50_Slope"] = (
                    _m_sma50_slope.get("value") if isinstance(_m_sma50_slope, dict) else None
                )
            _m_sma200 = mf.get("sma200")
            if isinstance(_m_sma200, dict):
                flat["Context_Macro_SMA_200"] = _m_sma200.get("price")
                _m_sma200_pd = _m_sma200.get("price_distance")
                flat["Context_Macro_Price_vs_SMA200"] = (
                    _m_sma200_pd.get("value") if isinstance(_m_sma200_pd, dict) else None
                )
            _m_gc = mf.get("golden_cross")
            if isinstance(_m_gc, dict):
                flat["Context_Macro_Golden_Cross"] = _m_gc.get("value")
            _m_ema = mf.get("ema")
            if isinstance(_m_ema, dict):
                flat["Context_Macro_EMA_8"]       = _m_ema.get("ema_8")
                flat["Context_Macro_EMA_21"]      = _m_ema.get("ema_21")
                flat["Context_Macro_EMA_Stacked"] = _m_ema.get("stacked")
            _m_ema50 = mf.get("ema_50")
            if isinstance(_m_ema50, dict):
                flat["Context_Macro_EMA_50"] = _m_ema50.get("price")
                _m_ema50_slope = _m_ema50.get("slope")
                flat["Context_Macro_EMA_50_Slope"] = (
                    _m_ema50_slope.get("value") if isinstance(_m_ema50_slope, dict) else None
                )
            _m_adx = mf.get("adx")
            if isinstance(_m_adx, dict):
                flat["Context_Macro_ADX"] = _m_adx.get("value")
            # [WKC-001 v1.1] market_stage sub-object replaces v1.0 stage_2.
            # Reverse-maps to BOTH the new Context_Macro_Stage_Classification
            # flat key AND the legacy Context_Macro_Stage2 / Context_Macro_Stage2_Definition
            # keys for backward compatibility.
            _m_ms = mf.get("market_stage")
            if isinstance(_m_ms, dict):
                _m_ms_stage = _m_ms.get("stage")
                if isinstance(_m_ms_stage, dict):
                    flat["Context_Macro_Stage_Classification"] = _m_ms_stage.get("label")
                flat["Context_Macro_Stage2"]            = _m_ms.get("stage_2_confirmed")
                flat["Context_Macro_Stage2_Definition"] = _m_ms.get("definition")

        # [UX-002] protective_anchor reverse-map removed (spec §4.3b). All three
        # flat keys re-homed: Daily_ATR + Daily_Protective_Anchor in the DAILY
        # higher_frame branch above; Daily_Hard_Stop in the stop-hierarchy
        # extraction block below (via the DAILY_HARD_STOP entry label).

        # PA-001 Phase 2: PE-CAL-3 exemption reverse mapping
        _pe_cal3 = fa.get("floor_proximity_exemption")
        if _pe_cal3 and isinstance(_pe_cal3, dict):
            flat["Floor_Proximity_Exempted"] = _pe_cal3.get("exempted")
            flat["Floor_Proximity_Exemption_Desc"] = _pe_cal3.get("desc")

    # --- SETUP-001: trade_setup extraction ---
    tsu = grouped.get("trade_setup", {})
    if tsu:
        _tgt = tsu.get("target", {})
        if isinstance(_tgt, dict):
            flat["Profit_Target"] = _tgt.get("price")
            _src = _tgt.get("source", {})
            flat["Profit_Target_Source"] = _src.get("label") if isinstance(_src, dict) else _src
            _role = _tgt.get("role", {})
            flat["Profit_Target_Role"] = _role.get("label") if isinstance(_role, dict) else _role
            # RISK-UX-001: intermediate is now {price, method, desc} or None
            _inter = _tgt.get("intermediate", {})
            if isinstance(_inter, dict):
                flat["Profit_Target_Synthetic"] = _inter.get("price")
            elif _inter is not None:
                flat["Profit_Target_Synthetic"] = _inter  # backward compat for bare value
            else:
                flat["Profit_Target_Synthetic"] = None
            # RISK-UX-001: blue_sky relocated from trade_risk
            _bs = _tgt.get("blue_sky", {})
            if isinstance(_bs, dict):
                flat["Blue_Sky_Detected"] = _bs.get("detected", False)
                flat["Blue_Sky_Method"] = _bs.get("method")
                flat["Blue_Sky_ATR_Headroom"] = _bs.get("atr_headroom")
                # Blue_Sky_Target = target.price when blue sky active
                if _bs.get("detected"):
                    flat["Blue_Sky_Target"] = _tgt.get("price")
                else:
                    flat["Blue_Sky_Target"] = None
            else:
                flat["Blue_Sky_Detected"] = False
                flat["Blue_Sky_Target"] = None
                flat["Blue_Sky_Method"] = None
                flat["Blue_Sky_ATR_Headroom"] = None
        _stp = tsu.get("stop", {})
        if isinstance(_stp, dict):
            flat["Hard_Stop"] = _stp.get("price")
            flat["Hard_Stop_Note"] = _stp.get("note")
            _adj = _stp.get("adjustment", {})
            if isinstance(_adj, dict):
                flat["Original_Hard_Stop"] = _adj.get("original_price")
                flat["Stop_Adjusted_Flag"] = _adj.get("adjusted")
                flat["Stop_Adjusted_Reason"] = _adj.get("reason")
                flat["Stop_Proximity_Blocked"] = _adj.get("proximity_blocked")
                flat["Stop_Gap_ATR"] = _adj.get("gap_atr")
        _ez = tsu.get("entry_zone", {})
        if isinstance(_ez, dict):
            _ref = _ez.get("reference", {})
            if isinstance(_ref, dict):
                flat["Entry_Reference"] = _ref.get("price")
            _epr = _ez.get("entry_price_range", {})
            if isinstance(_epr, dict):
                flat["Pullback_Zone_Upper"] = _epr.get("upper")
        _rally = tsu.get("rally", {})
        if isinstance(_rally, dict):
            _fibs = _rally.get("fibonacci_levels", {})
            if isinstance(_fibs, dict):
                _f382 = _fibs.get("level_382", {})
                _f500 = _fibs.get("level_500", {})
                flat["Fib_382_Level"] = _f382.get("price") if isinstance(_f382, dict) else None
                flat["Fib_500_Level"] = _f500.get("price") if isinstance(_f500, dict) else None
            _pm = _rally.get("projected_move", {})
            if isinstance(_pm, dict):
                flat["MM_Target"] = _pm.get("price")
            # [ENG-006] Reverse-map the three Fibonacci extension levels from the
            # rally.extensions sub-object (mirrors the Fib_382_Level pattern above)
            # so the _audit_key_coverage round-trip reconstructs them as scalars.
            _exts = _rally.get("extensions", {})
            if isinstance(_exts, dict):
                _e1272 = _exts.get("ext_1272", {})
                _e1618 = _exts.get("ext_1618", {})
                _e2618 = _exts.get("ext_2618", {})
                flat["Fib_Ext_1272_Level"] = _e1272.get("price") if isinstance(_e1272, dict) else None
                flat["Fib_Ext_1618_Level"] = _e1618.get("price") if isinstance(_e1618, dict) else None
                flat["Fib_Ext_2618_Level"] = _e2618.get("price") if isinstance(_e2618, dict) else None
            # PE-44: confluence (renamed from assessment)
            _conf = _rally.get("confluence", {})
            if isinstance(_conf, dict):
                flat["Fib_A_Confluence"] = _conf.get("label")
        _ew = tsu.get("execution_window", {})
        if isinstance(_ew, dict):
            flat["window_count"] = _ew.get("current")
            flat["Window_Limit"] = _ew.get("limit")
            flat["Window_Reset_Event"] = _ew.get("reset_event")
            flat["Window_Timeframe"] = _ew.get("timeframe")
            flat["Window_Status"] = _ew.get("status")

    # --- EXT-001: extension_analysis extraction ---
    if ext:
        _dist = ext.get("distance", {})
        flat["ATR_Dist"] = _dist.get("value") if isinstance(_dist, dict) else None
        _anc = ext.get("anchor", {})
        flat["ATR_Dist_Anchor"] = _anc.get("label") if isinstance(_anc, dict) else None
        _lim = ext.get("limit", {})
        flat["Extension_Limit"] = _lim.get("value") if isinstance(_lim, dict) else None
        # BKOUT-001: effective limit for backward compat
        _eff = _lim.get("effective") if isinstance(_lim, dict) else None
        if _eff is not None:
            flat["Extension_Limit_Effective"] = _eff
        # EXT-OBS-001: condition label
        _cond = ext.get("condition", {})
        if isinstance(_cond, dict):
            flat["Extension_Condition"] = _cond.get("label")

        # PA-001 Phase 2: daily extension reverse mapping
        _daily = ext.get("daily")
        if _daily and isinstance(_daily, dict):
            _dd = _daily.get("distance", {})
            flat["Daily_Extension_Distance"] = _dd.get("value") if isinstance(_dd, dict) else None
            _dc = _daily.get("condition", {})
            flat["Daily_Extension_Label"] = _dc.get("label") if isinstance(_dc, dict) else None
            if "caution_note" in _daily:
                flat["Daily_Extension_Caution_Note"] = _daily["caution_note"]
            # [PCT-001] Profile A percentage-distance from Daily EMA 21.
            # Flattened from extension_analysis.daily.distance_pct grouped field.
            _ddp = _daily.get("distance_pct") if isinstance(_daily, dict) else None
            flat["Pct_From_Daily_EMA21"] = _ddp.get("value") if isinstance(_ddp, dict) else None
            # PA-001 Phase 2: Daily RSI reverse mapping
            _rsi = _daily.get("rsi")
            if _rsi and isinstance(_rsi, dict):
                _rv = _rsi.get("value", {})
                flat["Daily_RSI"] = _rv.get("value") if isinstance(_rv, dict) else None
                _ra = _rsi.get("admissibility", {})
                flat["Daily_RSI_Admissibility"] = _ra.get("label") if isinstance(_ra, dict) else None
                flat["Daily_RSI_Admissibility_Desc"] = _ra.get("desc") if isinstance(_ra, dict) else None

        # PA-001 Phase 4 DQ-11: medium-term extension reverse mapping
        _mt = ext.get("medium_term")
        if _mt and isinstance(_mt, dict):
            _md = _mt.get("distance", {})
            flat["MediumTerm_Extension_Pct"] = _md.get("value") if isinstance(_md, dict) else None
            # [PCT-001 DQ-8] Cross-profile naming alias -- Profile B emits canonical
            # name alongside legacy MediumTerm_Extension_Pct. Single-value alias only --
            # Label and Caution_Note siblings retain legacy naming (deprecation
            # deferred to future hygiene pass per DQ-8 scope guard). On Profile A,
            # the medium_term block produces the same %-distance value (Profile A
            # medium_term block has only distance+anchor; no condition/caution),
            # so the alias covers both profile paths uniformly.
            flat["Pct_From_Daily_SMA50"] = flat.get("MediumTerm_Extension_Pct")
            _mc = _mt.get("condition", {})
            flat["MediumTerm_Extension_Label"] = _mc.get("label") if isinstance(_mc, dict) else None
            if "caution_note" in _mt:
                flat["MediumTerm_Extension_Caution_Note"] = _mt["caution_note"]

    # --- PSY-002: psychological_levels extraction ---
    psy = grouped.get("psychological_levels", {})
    if psy:
        _pf = psy.get("floor", {})
        if isinstance(_pf, dict):
            flat["Psych_Floor"] = _pf.get("price")
            flat["Psych_Floor_Dist_Pct"] = _pf.get("distance_pct")
            flat["Psych_Floor_Near_Technical"] = _pf.get("near_structural_floor")
        _pc = psy.get("ceiling", {})
        if isinstance(_pc, dict):
            flat["Psych_Ceiling"] = _pc.get("price")
            flat["Psych_Ceiling_Near_Technical"] = _pc.get("near_resistance")
        _at = psy.get("at_target", {})
        flat["RN_Target_Proximity"] = _at.get("label") if isinstance(_at, dict) else _at
        _ast = psy.get("at_stop", {})
        flat["RN_Stop_Proximity"] = _ast.get("label") if isinstance(_ast, dict) else _ast
        _af = psy.get("at_floor", {})
        flat["RN_Floor_Proximity"] = _af.get("label") if isinstance(_af, dict) else _af

    # --- entry_proximity: custom extraction (PROX-001) ---
    ep = grouped.get("entry_proximity", {})
    if ep:
        _sig = ep.get("signal", {})
        flat["Proximity_Signal"] = _sig.get("label") if isinstance(_sig, dict) else _sig
        _bc = ep.get("blocking_condition", {})
        if isinstance(_bc, dict):
            flat["Proximity_Blocking_Gate"] = _bc.get("label")
        _dist_obj = ep.get("distance", {})
        if isinstance(_dist_obj, dict):
            flat["Proximity_Distance"] = _dist_obj.get("value")
        _tgt = ep.get("target", {})
        if isinstance(_tgt, dict):
            flat["Proximity_Target"] = _tgt.get("value")
        if "note" in ep:
            flat["Proximity_Note"] = ep["note"]

    # --- exit_signals: custom extraction (EXIT-001) ---
    ex = grouped.get("exit_signals", {})
    if ex:
        _es_sig = ex.get("signal", {})
        flat["Exit_Signal"] = _es_sig.get("label") if isinstance(_es_sig, dict) else _es_sig
        flat["Exit_Triggers"] = ex.get("triggers")
        flat["Exit_Reason"] = ex.get("reason")
        _vwap_c = ex.get("vwap_counter", {})
        if isinstance(_vwap_c, dict):
            _vc_val = _vwap_c.get("value")
            _vc_thr = _vwap_c.get("threshold", 3)
            flat["Exit_VWAP_Counter"] = f"{_vc_val}/{_vc_thr}" if _vc_val is not None else None
        # AVWAP-001 Phase 3 T4: ema21_counter replaces vwap_counter
        _ema21_c = ex.get("ema21_counter", {})
        if isinstance(_ema21_c, dict):
            _e21_val = _ema21_c.get("value")
            _e21_thr = _ema21_c.get("threshold", 3)
            flat["Exit_EMA21_Counter"] = f"{_e21_val}/{_e21_thr}" if _e21_val is not None else None
        _ema8_c = ex.get("ema8_counter", {})
        if isinstance(_ema8_c, dict):
            _ec_val = _ema8_c.get("value")
            _ec_thr = _ema8_c.get("threshold", 2)
            flat["Exit_EMA8_Counter"] = f"{_ec_val}/{_ec_thr}" if _ec_val is not None else None
        _elow = ex.get("established_low", {})
        if isinstance(_elow, dict):
            flat["Established_Hourly_Low"] = _elow.get("price")

    _unmap(grouped.get("_debug", {}), _GROUP_DEBUG)

    # AS-001: entry_strategy from action_summary (VALID only)
    es = _as.get("entry_strategy")
    if es and es.get("entry_price") is not None:
        flat["Entry_Reference"] = es["entry_price"]
    if es and es.get("stop_loss") is not None:
        flat["Hard_Stop"] = es["stop_loss"]
    if es and es.get("target") is not None:
        flat["Profit_Target"] = es["target"]

    # AS-001: exit_status extraction (replaces existing_position_exit_*)
    _exit_st = _as.get("exit_status", {})
    if isinstance(_exit_st, dict):
        if _exit_st.get("active") is not None:
            flat["Exit_Signal_Active"] = _exit_st["active"]
        if _exit_st.get("reason") and _exit_st.get("active"):
            flat["Exit_Reason_Summary"] = _exit_st["reason"]

    # VTRIG-001: volume_confirmation from action_summary (all paths)
    _vc = _as.get("volume_confirmation")
    if _vc and isinstance(_vc, dict):
        flat["Vol_Confirm_Tier"] = _vc.get("liquidity_tier")
        flat["Vol_Confirm_Multiplier"] = _vc.get("multiplier")
        # adv_20_shares maps back to ADV_20 which is already populated from trade_snapshot
        _cps = _vc.get("checkpoints", {})
        for cp_key in ("15m", "30m", "60m"):
            cp = _cps.get(cp_key, {})
            flat[f"Vol_Confirm_{cp_key}"] = cp.get("min_shares")

    # SFR-001: signal_freshness from action_summary (VALID / RECOVERY CANDIDATE)
    _sfr = _as.get("signal_freshness")
    if _sfr and isinstance(_sfr, dict):
        flat["Signal_Freshness"] = _sfr.get("label")

    # CQS-001: consolidation_quality from action_summary (VALID breakout paths)
    _cqs = _as.get("consolidation_quality")
    if _cqs and isinstance(_cqs, dict):
        _cqs_comp = _cqs.get("composite", {})
        flat["CQS_Composite_Score"] = _cqs_comp.get("score")
        flat["CQS_Composite_Label"] = _cqs_comp.get("label")
        _cqs_components = _cqs.get("components", {})
        _rc = _cqs_components.get("range_contraction", {})
        flat["CQS_Range_Contraction_Score"] = _rc.get("score")
        _vc = _cqs_components.get("volume_contraction", {})
        flat["CQS_Volume_Contraction_Score"] = _vc.get("score")
        _vcp = _cqs_components.get("vcp_proxy", {})
        flat["CQS_VCP_Score"] = _vcp.get("score")
        _cqs_diag = _cqs.get("diagnostics", {})
        flat["CQS_ATR_Gate_Passed"] = _cqs_diag.get("atr_gate_passed")
        flat["CQS_ATR_Ratio"] = _cqs_diag.get("atr_ratio")
        flat["CQS_VCP_Swing_Lows_Found"] = _cqs_diag.get("swing_lows_found")
        flat["CQS_Volume_Terminal_Ratio"] = _cqs_diag.get("volume_terminal_ratio")
    # CQS CAUTION note from caution_factors
    _caution_factors = _as.get("caution_factors", [])
    for _cf in _caution_factors:
        if isinstance(_cf, dict) and _cf.get("factor") == "CQS_LOW_QUALITY":
            flat["CQS_Caution_Note"] = _cf.get("desc")
            break

    # IVR-001: volatility_regime extraction (5 flat keys — Spec §6.3)
    _vr = grouped.get("volatility_regime", {})
    if _vr:
        _vr_iv = _vr.get("iv", {})
        flat["IV_Current"] = _vr_iv.get("value") if isinstance(_vr_iv, dict) else None
        _vr_hv = _vr.get("hv", {})
        flat["HV_30D"] = _vr_hv.get("value") if isinstance(_vr_hv, dict) else None
        _vr_ratio = _vr.get("ratio", {})
        flat["IV_HV_Ratio"] = _vr_ratio.get("value") if isinstance(_vr_ratio, dict) else None
        _vr_regime = _vr.get("regime", {})
        flat["Volatility_Regime"] = _vr_regime.get("label") if isinstance(_vr_regime, dict) else None
        _vr_ci = _vr.get("context_interpretation", {})
        _vr_interp = _vr_ci.get("interpretation", {}) if isinstance(_vr_ci, dict) else {}
        flat["Volatility_Interpretation"] = _vr_interp.get("label") if isinstance(_vr_interp, dict) else None
    # IVR-001: caution factor from caution_factors
    for _cf in _caution_factors:
        if isinstance(_cf, dict) and _cf.get("factor") == "VOLATILITY_REGIME":
            flat["Volatility_Caution_Factor"] = _cf.get("desc")
            break

    # RLY-001: rally_state reverse-mapping (8 flat keys — Spec §3.3)
    _rs = grouped.get("rally_state")
    if isinstance(_rs, dict):
        _rs_primary = _rs.get("primary") or {}
        _rs_context = _rs.get("context") or {}
        _rs_magnitude = _rs.get("magnitude") or {}
        _rs_maturity = _rs.get("maturity") or {}
        flat["Rally_Up_Bar_Count_Primary"] = _rs_primary.get("up_bar_count")
        flat["Rally_Up_Bar_Count_Context"] = _rs_context.get("up_bar_count")
        flat["Rally_Up_Bar_Ratio_Primary"] = _rs_primary.get("ratio")
        flat["Rally_Up_Bar_Ratio_Context"] = _rs_context.get("ratio")
        flat["Rally_Window_Bars"] = _rs_primary.get("window_bars") or _rs_context.get("window_bars")
        flat["Rally_Magnitude_ATR"] = _rs_magnitude.get("atr_widths")
        flat["Rally_Anchor_Price"] = _rs_magnitude.get("anchor_price")
        flat["Rally_Maturity_Label"] = _rs_maturity.get("label")
    else:
        for _rk in (
            "Rally_Up_Bar_Count_Primary", "Rally_Up_Bar_Count_Context",
            "Rally_Up_Bar_Ratio_Primary", "Rally_Up_Bar_Ratio_Context",
            "Rally_Window_Bars", "Rally_Magnitude_ATR",
            "Rally_Anchor_Price", "Rally_Maturity_Label",
        ):
            flat[_rk] = None

    # REC-001 Phase 2D: recovery_analysis extraction with Recovery_ prefix
    _ra = grouped.get("recovery_analysis", {})
    if _ra:
        flat["Recovery_Status"]                  = _ra.get("recovery_status")
        flat["Recovery_Base_Bar_Count"]           = _ra.get("base_bar_count")
        flat["Recovery_Swing_Low_Price"]          = _ra.get("swing_low_price")
        flat["Recovery_Swing_Low_Bar_Index"]      = _ra.get("swing_low_bar_index")
        flat["Recovery_EMA_Cross_Bar_Index"]      = _ra.get("ema_cross_bar_index")
        flat["Recovery_DI_Spread_Current"]        = _ra.get("di_spread_current")
        flat["Recovery_DI_Spread_At_Swing_Low"]   = _ra.get("di_spread_at_swing_low")
        flat["Recovery_ATR_Contraction_Ratio"]    = _ra.get("atr_contraction_ratio")
        flat["Recovery_Retest_Confirmed"]         = _ra.get("retest_confirmed")
        flat["Recovery_Time_Stop_Bars_Remaining"] = _ra.get("time_stop_bars_remaining")
        flat["Recovery_Target"]                   = _ra.get("recovery_target")
        flat["Recovery_Target_Source"]             = _ra.get("recovery_target_source")
        flat["Recovery_Active_Count"]             = _ra.get("recovery_active_count")
        flat["Recovery_Capital_RR"]               = _ra.get("recovery_capital_rr")
        flat["Recovery_CRG_Bypass_Context"]       = _ra.get("crg_bypass_context")
        flat["Recovery_Diagnostic"]               = _ra.get("diagnostic")

    # SBO-001 Phase 2: swing_breakout_confirmation extraction
    # BRK-001-GAP-2: The section may exist as a minimal container carrying
    # only breakout_thesis (Option A) when SBO is inactive. Guard SBO-field
    # extraction on breakout_age presence so partial containers round-trip
    # SBO keys as the None they were originally emitted as (output.py
    # defaults for non-A-non-ETF paths) rather than False derived from an
    # absent status label.
    _sbo = grouped.get("swing_breakout_confirmation")
    if _sbo and _sbo.get("breakout_age") is not None:
        _sbo_status = _sbo.get("status", {})
        _sbo_age_obj = _sbo.get("breakout_age", {})
        _sbo_window = _sbo.get("confirmation_window", {})
        _sbo_rvol_obj = _sbo.get("breakout_rvol", {})
        _sbo_label = _sbo_status.get("label") if isinstance(_sbo_status, dict) else _sbo_status
        flat["SBO_Breakout_Bar_Age"] = _sbo_age_obj.get("value") if isinstance(_sbo_age_obj, dict) else _sbo_age_obj
        flat["SBO_Trending_Reached"] = (_sbo_label == "CONFIRMED")
        flat["SBO_Confirmation_Timeout"] = (_sbo_label == "EXPIRED")
        flat["SBO_RVOL"] = _sbo_rvol_obj.get("value") if isinstance(_sbo_rvol_obj, dict) else _sbo_rvol_obj

    # BRK-001-GAP-2: breakout_thesis sub-object extraction
    _sbo_thesis = _sbo.get("breakout_thesis") if _sbo else None
    if _sbo_thesis:
        _thesis_status_obj = _sbo_thesis.get("status", {})
        flat["Breakout_Thesis_Status"] = (
            _thesis_status_obj.get("label")
            if isinstance(_thesis_status_obj, dict)
            else _thesis_status_obj
        )
        flat["BRK_Thesis_New_Support"] = _sbo_thesis.get("new_support")
        flat["BRK_Thesis_Bar_Close"] = _sbo_thesis.get("bar_close")
        flat["BRK_Thesis_Delta"] = _sbo_thesis.get("delta")

    # PA-001 Phase 3: target_hierarchy and floor_hierarchy extraction (DQ-9, DQ-10)
    # Nested under trade_setup.target.hierarchy and trade_setup.stop.hierarchy
    _tgt_obj = tsu.get("target", {}) if tsu else {}
    _th = _tgt_obj.get("hierarchy") if isinstance(_tgt_obj, dict) else None
    if _th and isinstance(_th, list):
        flat["Target_Hierarchy_Count"] = len(_th)
        flat["Target_Hierarchy_Winner"] = next(
            (e["label"] for e in _th if e.get("escalation_winner")), None
        )
    else:
        flat["Target_Hierarchy_Count"] = 0
        flat["Target_Hierarchy_Winner"] = None

    _stp_obj = tsu.get("stop", {}) if tsu else {}
    _fh = _stp_obj.get("hierarchy") if isinstance(_stp_obj, dict) else None
    if _fh and isinstance(_fh, list):
        flat["Floor_Hierarchy_Count"] = len(_fh)
        # [UX-002] Re-home Daily_Hard_Stop reverse-map entry (spec §4.3b).
        # Source: stop-hierarchy entry with label == "DAILY_HARD_STOP" (only
        # emitted on Profile A per transform.py:3410's > 0 guard).
        _dhs_entry = next(
            (e for e in _fh if isinstance(e, dict) and e.get("label") == "DAILY_HARD_STOP"),
            None,
        )
        if _dhs_entry is not None:
            flat["Daily_Hard_Stop"] = _dhs_entry.get("price")
    else:
        flat["Floor_Hierarchy_Count"] = 0

    return status, diagnostic, flat


# ---------------------------------------------------------------------------
# Key coverage audit
# ---------------------------------------------------------------------------

def _audit_key_coverage(flat_metrics: dict) -> list:
    unmapped = set(flat_metrics.keys()) - MAPPED_FLAT_KEYS
    unmapped.discard("df_ctx")
    unmapped.discard("metrics")
    return sorted(unmapped)

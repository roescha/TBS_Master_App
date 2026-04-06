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
    ("Context_Weekly_Golden_Cross",   "golden_cross"),
    ("Context_Weekly_Price_vs_SMA200","price_vs_sma200"),
    ("Context_Weekly_SMA50",          "sma50"),
    ("Context_Weekly_SMA50_Slope",    "sma50_slope"),
    ("Context_Weekly_SMA50_Rising",   "sma50_rising"),
    ("Context_Monthly_Golden_Cross",  "golden_cross"),
    ("Context_Monthly_Price_vs_SMA200","price_vs_sma200"),
    ("Context_Monthly_SMA200",        "sma200"),
    ("Context_Monthly_SMA50",         "sma50"),
    ("Context_Monthly_SMA50_Slope",   "sma50_slope"),
]

_HIGHER_FRAME_ALL_KEYS = sorted(set(gk for _, gk in _HIGHER_FRAME_MAP))


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
        "Exit_VWAP_Counter", "Exit_EMA8_Counter", "Established_Hourly_Low",
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
    # FA-001: floor_analysis keys
    keys.update([
        "Floor_Failure_Context", "Floor_Breach_Dist", "Floor_Failure_Reclaim",
        "Floor_Failure_Threshold", "Anchor_Label", "Anchor_Type", "Floor_Anchor_Type",
        "Floor_Anchor_Label", "Extension_Anchor_Type", "Extension_Anchor_Label",
        "Floor_Failure_Status_Label", "Floor_Failure_Status_Desc",
        "Floor_Prox_Pct",
        "Context_EMA_8", "Context_EMA_21", "Context_EMA_Stacked",
        "Context_EMA_Bias", "Context_EMA_Bias_Desc", "Context_SMA50_Slope_Bias",
    ])
    # SNAP-001: trade_snapshot keys (price_indicators absorbed)
    keys.update([
        "Price", "Structural_Floor", "Resistance", "ADV_20",
        "EMA_8", "EMA_21", "SMA_50", "SMA_200", "VWAP", "ATR",
        "Convexity_Class", "ETF_Primary_Exchange", "ETF_Detection_Source", "Is_ETF",
    ])
    # SETUP-001: trade_setup keys
    keys.update([
        "Profit_Target", "Profit_Target_Source", "Profit_Target_Role",
        "Profit_Target_Synthetic", "Profit_Target_Synthetic_Note",
        "Hard_Stop", "Hard_Stop_Note", "Original_Hard_Stop",
        "Stop_Adjusted_Flag", "Stop_Adjusted_Reason",
        "Pullback_Zone_Upper", "Cons_High", "Resistance_Note",
        "Fib_382_Level", "Fib_500_Level", "Fib_Confluence",
        "Fib_A_382_Level", "Fib_A_500_Level", "Fib_A_Confluence",
        "MM_Target", "MM_Rally_ATR",
        "Window_Limit", "Window_Reset_Event", "window_count",
    ])
    # EXT-001: extension_analysis keys
    keys.update([
        "ATR_Dist", "ATR_Dist_Anchor", "ATR_Dist_Note",
        "Extension_Limit", "Trend_Quality_Override",
    ])
    # PSY-002: psychological_levels keys
    keys.update([
        "Psych_Floor", "Psych_Ceiling", "Psych_Floor_Dist_Pct",
        "Psych_Floor_Near_Technical", "Psych_Floor_Near_Structural",
        "Psych_Ceiling_Near_Technical", "Psych_Increment", "Psych_Ceiling_Dist_Pct",
        "RN_Target_Proximity", "RN_Stop_Proximity", "RN_Floor_Proximity",
    ])

    return keys

MAPPED_FLAT_KEYS = _all_mapped_flat_keys()


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
    _price_levels = {
        "ema_8": {"price": flat_metrics.get("EMA_8"), "desc": "Short-term trend (8-period EMA)"},
        "ema_21": {"price": flat_metrics.get("EMA_21"), "desc": "Medium-term trend (21-period EMA)"},
        "sma_50": {"price": flat_metrics.get("SMA_50"), "desc": "Intermediate trend support (~2 months)"},
        "sma_200": {"price": flat_metrics.get("SMA_200"), "desc": "Long-term trend support (~10 months)"},
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

    trade_snapshot = {
        "price": {
            "current": _current_price,
            "bar_close": _pe42_bar_close,
            "source": {"label": _pe42_price_source, "desc": _price_source_desc},
        },
        "structural_floor": {"price": flat_metrics.get("Structural_Floor"), "desc": _struct_floor_desc},
        "resistance": {"price": _resistance_price, "desc": _resistance_desc_final},
        "atr": {"value": flat_metrics.get("ATR"), "period": 14, "desc": "Average True Range (14-period) -- unit of measurement for distances and thresholds"},
        "avg_daily_volume": {"value": flat_metrics.get("ADV_20"), "unit": "shares", "desc": "20-day average daily volume"},
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
        "floor_proximity_pct": {"value": flat_metrics.get("Floor_Prox_Pct"), "unit": "%", "desc": "Price distance from structural floor as percentage"} if flat_metrics.get("Floor_Prox_Pct") is not None else None,
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
    elif _has_weekly:
        _hf_timeframe = "WEEKLY"
        _hf_tf_desc = "Context frame for structural regime"
        _hf_sma50_price = flat_metrics.get("Context_Weekly_SMA50")
        _hf_sma50_slope = flat_metrics.get("Context_Weekly_SMA50_Slope")
        _hf_sma200_price = None
        _hf_golden_cross = flat_metrics.get("Context_Weekly_Golden_Cross")
        _hf_price_vs_sma200 = flat_metrics.get("Context_Weekly_Price_vs_SMA200")
    elif _has_monthly:
        _hf_timeframe = "MONTHLY"
        _hf_tf_desc = "Context frame for structural regime"
        _hf_sma50_price = flat_metrics.get("Context_Monthly_SMA50")
        _hf_sma50_slope = flat_metrics.get("Context_Monthly_SMA50_Slope")
        _hf_sma200_price = flat_metrics.get("Context_Monthly_SMA200")
        _hf_golden_cross = flat_metrics.get("Context_Monthly_Golden_Cross")
        _hf_price_vs_sma200 = flat_metrics.get("Context_Monthly_Price_vs_SMA200")
    else:
        _hf_timeframe = None
        _hf_tf_desc = ""
        _hf_sma50_price = None
        _hf_sma50_slope = None
        _hf_sma200_price = None
        _hf_golden_cross = None
        _hf_price_vs_sma200 = None

    _sma50_slope_bias = flat_metrics.get("Context_SMA50_Slope_Bias")
    _sma50_slope_bias_desc = ""
    if _sma50_slope_bias == "BULLISH":
        _sma50_slope_bias_desc = f"{_hf_timeframe or ''} SMA 50 rising".strip()
    elif _sma50_slope_bias == "BEARISH":
        _sma50_slope_bias_desc = f"{_hf_timeframe or ''} SMA 50 declining".strip()

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
        if _hf_sma200_price is not None:
            higher_frame["sma200"] = {
                "price": _hf_sma200_price,
                "price_distance": {"value": _hf_price_vs_sma200, "unit": "dollars", "desc": f"{_hf_timeframe} close distance from {_hf_timeframe} SMA 200"} if _hf_price_vs_sma200 is not None else None,
                "desc": f"{_hf_timeframe} SMA 200",
            }

    floor_analysis["higher_frame"] = higher_frame if higher_frame else None

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
        "avg_daily_dollar_volume": {"value": flat_metrics.get("ADV_20_Dollar"), "unit": "USD", "desc": "20-day average daily dollar volume"},
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

    _ts_directional = {
        "adx": {
            "value": flat_metrics.get("ADX"),
            "threshold": 20,
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

    _crr_status_desc_map = {
        "HEALTHY": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
        "NARROW": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
        "INSUFFICIENT": "Capital R:R >= 1.5. Below 1.5: NARROW. Below 1.0: INSUFFICIENT (entry blocked)",
    }

    trade_risk = {
        "summary": {
            "label": flat_metrics.get("Risk_Summary_Label"),
            "desc": flat_metrics.get("Risk_Summary_Desc"),
        },
        "price_reward_risk": {
            "value": _rr_val,
            "threshold": {
                "value": _exp_threshold if _exp_threshold is not None else 2.0,
                "note": _exp_threshold_note,
                "desc": "Minimum structural R:R -- below: INVALID, at or above: entry permitted",
            },
            "note": flat_metrics.get("Reward_Risk_Note"),
            "desc": "Price R:R -- reward (resistance - price) / risk (price - floor)",
        },
        "capital_reward_risk": {
            "value": _crr_val,
            "status": {
                "label": _crr_label_val,
                "desc": _crr_status_desc_map.get(_crr_label_val or "", ""),
            },
            "desc": "Capital R:R -- reward (target - price) / risk (price - hard stop)",
        },
        "risk_per_unit": flat_metrics.get("Risk_Per_Unit"),
    }

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
    _vwap_counter = flat_metrics.get("Exit_VWAP_Counter")
    if _vwap_counter is not None:
        # Parse "0/3" -> integer 0
        _vwap_int = int(_vwap_counter.split("/")[0]) if isinstance(_vwap_counter, str) and "/" in _vwap_counter else _vwap_counter
        exit_signals["vwap_counter"] = {
            "value": _vwap_int,
            "threshold": 3,
            "desc": "Consecutive closes below VWAP (3 triggers EXIT)",
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

    _target_obj = {
        "price": _profit_target,
        "source": {"label": _profit_target_source, "desc": _profit_target_source or ""},
        "role": {"label": _role_label, "desc": _role_desc} if _profit_target_role else None,
        "intermediate": flat_metrics.get("Profit_Target_Synthetic"),
    } if _profit_target is not None else None

    _stop_adj = None
    if _stop_adjusted:
        _stop_adj = {
            "original_price": _original_stop,
            "adjusted": True,
            "reason": _stop_reason,
            "desc": f"Structural stop audit -- stop adjusted for {(_stop_reason or 'proximity').split('--')[0].strip().lower()}",
        }

    _stop_obj = {
        "price": _hard_stop,
        "note": flat_metrics.get("Hard_Stop_Note"),
        "desc": "Floor - 1.5 ATR (maximum loss level)",
        "adjustment": _stop_adj,
    }

    # Entry zone (trigger-aware)
    _entry_ref = flat_metrics.get("Entry_Reference")
    _pb_upper = flat_metrics.get("Pullback_Zone_Upper")
    _window_reset = flat_metrics.get("Window_Reset_Event", "")
    _trigger_type = _window_reset.split(" + ")[0] if _window_reset else ""

    # VS-17: reference.desc per trigger type
    _is_pullback = _trigger_type.upper() == "PULLBACK" if _trigger_type else False
    _is_breakout = _trigger_type.upper() == "BREAKOUT" if _trigger_type else False
    _is_reclaim = _trigger_type.upper() == "RECLAIM" if _trigger_type else False

    if _is_pullback:
        _ref_desc = flat_metrics.get("Anchor_Label", "")
    elif _is_breakout:
        _ref_desc = "Resistance level"
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

    if _is_pullback:
        _ez_desc = "Close within pullback zone (" + _ez_bar_label + ")"
    elif _is_breakout:
        _ez_desc = "Close above resistance (" + _ez_bar_label + ")" if _ez_bar_label != "weekly bar" else ""
    elif _is_reclaim:
        _ez_desc = "Close above structural floor (3 bars required)" if _ez_bar_label != "weekly bar" else ""
    else:
        _ez_desc = ""

    # VS-09: entry_price_range.desc per profile
    if "SWING" in str(_db).upper():
        _epr_desc = "Floor to floor + 0.5 ATR"
    elif "WEALTH" in str(_db).upper():
        _epr_desc = "Floor to floor + 0.5 ATR"
    else:
        _epr_desc = "Floor to EMA 21 + 0.5 ATR"

    # VS-14: entry_price_range only on PULLBACK triggers
    # VS-04: Guard for EMA inversion on broken structures
    _ez_inverted = (_entry_ref is not None and _pb_upper is not None and _entry_ref > _pb_upper)
    _entry_zone = {
        "trigger": _trigger_type if _trigger_type else None,
        "reference": {"price": _entry_ref, "desc": _ref_desc} if _entry_ref else None,
        "entry_price_range": {
            "lower": _entry_ref,
            "upper": _pb_upper,
            "desc": _epr_desc,
        } if (_pb_upper and _is_pullback and not _ez_inverted) else None,
        "desc": _ez_desc + " [INVERTED: EMA structure broken]" if (_is_pullback and _ez_inverted) else _ez_desc,
    }

    # Rally (Profile A SWING + B TRENDING non-ETF only)
    _fib_382 = flat_metrics.get("Fib_A_382_Level") or flat_metrics.get("Fib_382_Level")
    _fib_500 = flat_metrics.get("Fib_A_500_Level") or flat_metrics.get("Fib_500_Level")
    _fib_conf = flat_metrics.get("Fib_A_Confluence") or flat_metrics.get("Fib_Confluence")
    _mm_target = flat_metrics.get("MM_Target")
    _mm_rally_atr = flat_metrics.get("MM_Rally_ATR")

    _rally_obj = None
    if _fib_382 is not None or _fib_500 is not None or _mm_target is not None:
        _rally_obj = {
            "assessment": {
                "trigger": _trigger_type,
                "label": _fib_conf,
                "desc": "",
            },
            "fibonacci_levels": {
                "level_382": {"price": _fib_382, "desc": "38.2% -- shallow pullback boundary"} if _fib_382 else None,
                "level_500": {"price": _fib_500, "desc": "50% -- deep pullback boundary"} if _fib_500 else None,
            } if (_fib_382 is not None or _fib_500 is not None) else None,
            "projected_move": {
                "price": _mm_target,
                "desc": "Measured move target -- next leg equals prior rally",
            } if _mm_target else None,
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
    }

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

    # --- Final result dict (12 sections per Batch 2) ---
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
        "entry_proximity":      entry_proximity,
        "exit_signals":         exit_signals,
    }
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

    # EXT-001: overextension_exception backward compat
    ext = grouped.get("extension_analysis", {})
    if ext:
        _override = ext.get("override", {})
        if isinstance(_override, dict):
            flat["Trend_Quality_Override"] = _override

    # --- trade_risk: custom extraction (RISK-001) ---
    tr = grouped.get("trade_risk", {})
    if tr:
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
        flat["Risk_Per_Unit"] = tr.get("risk_per_unit")

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
            elif _tf_label == "WEEKLY":
                if isinstance(_gc, dict): flat["Context_Weekly_Golden_Cross"] = _gc.get("value")
                if isinstance(_s50, dict):
                    flat["Context_Weekly_SMA50"] = _s50.get("price")
                    _sl = _s50.get("slope", {})
                    flat["Context_Weekly_SMA50_Slope"] = _sl.get("value") if isinstance(_sl, dict) else None
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
            flat["Profit_Target_Synthetic"] = _tgt.get("intermediate")
        _stp = tsu.get("stop", {})
        if isinstance(_stp, dict):
            flat["Hard_Stop"] = _stp.get("price")
            flat["Hard_Stop_Note"] = _stp.get("note")
            _adj = _stp.get("adjustment", {})
            if isinstance(_adj, dict):
                flat["Original_Hard_Stop"] = _adj.get("original_price")
                flat["Stop_Adjusted_Flag"] = _adj.get("adjusted")
                flat["Stop_Adjusted_Reason"] = _adj.get("reason")
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

    return status, diagnostic, flat


# ---------------------------------------------------------------------------
# Key coverage audit
# ---------------------------------------------------------------------------

def _audit_key_coverage(flat_metrics: dict) -> list:
    unmapped = set(flat_metrics.keys()) - MAPPED_FLAT_KEYS
    unmapped.discard("df_ctx")
    unmapped.discard("metrics")
    return sorted(unmapped)

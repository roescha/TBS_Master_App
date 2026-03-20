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
#   current_price, support, resistance, avg_daily_volume, classification{}
# DIAG-001 Phase 2B (DD-3): entry_strategy REMOVED — now in action_summary (VALID only)
# Classification sub-object: type (derived from Is_ETF), convexity, exchange, etf_detection

_GROUP_TRADE_SNAPSHOT_MAPPED = [
    ("Price",                  "current_price"),
    ("ADV_20",                 "avg_daily_volume"),
]

_GROUP_TRADE_SNAPSHOT_CLASSIFICATION = [
    ("Is_ETF",                 "is_etf"),
    ("Convexity_Class",        "convexity"),
    ("ETF_Primary_Exchange",   "exchange"),
    ("ETF_Detection_Source",   "etf_detection"),
]


# ===== TRADE_QUALITY (10 keys — 2 scalars + 2 sub-groups) =====

_TQ_TREND_HEALTH = [
    ("Trend_Health_Score",     "score"),
    ("THS_Label",              "label"),
    ("THS_Floor_Buffer",       "floor_buffer"),
    ("THS_Dir_Momentum",       "dir_momentum"),
    ("THS_Trend_Age",          "trend_age"),
    ("THS_Structure",          "structure"),
]

_TQ_VOLUME = [
    ("Vol_Confirm_Ratio",      "relative_volume"),
    ("Vol_Confirm_State",      "state"),
]

_TQ_SCALARS = [
    ("Conviction",                  "range_quality"),
    ("Trend_Quality_Override",      "overextension_exception"),
]

_TRADE_QUALITY_SUBGROUPS = [
    ("trend_health",    _TQ_TREND_HEALTH),
    ("volume",          _TQ_VOLUME),
]

_TQ_TOTAL = sum(len(t) for _, t in _TRADE_QUALITY_SUBGROUPS) + len(_TQ_SCALARS)
assert _TQ_TOTAL == 10


# ===== TRADE_RISK (7 keys — flat) =====

_GROUP_TRADE_RISK = [
    ("Reward_Risk",                 "ratio"),
    ("Reward_Risk_Note",            "note"),
    ("Capital_Reward_Risk",         "capital_ratio"),
    ("Capital_RR_Label",            "capital_label"),
    ("Risk_Per_Unit",               "risk_per_unit"),
    ("Expectancy_Threshold",        "threshold"),
    ("Expectancy_Threshold_Note",   "threshold_note"),
]
assert len(_GROUP_TRADE_RISK) == 7


# ===== TREND_STATE (9 keys — 2 sub-groups) =====

_TS_CLASSIFICATION = [
    ("Engine_State",           "state"),
    ("Trend_Age_Bars",         "age_bars"),
    ("Active_Modifiers",       "modifiers"),
    ("Inst_Churn",             "churn"),                    # SEM-001
]

_TS_DIRECTIONAL = [
    ("ADX",                    "adx"),
    ("ADX_Accel",              "accel"),
    ("ADX_Accel_State",        "accel_state"),
    ("DI_Plus",                "di_plus"),
    ("DI_Minus",               "di_minus"),
]

_TREND_STATE_SUBGROUPS = [
    ("classification",  _TS_CLASSIFICATION),
    ("directional",     _TS_DIRECTIONAL),
]

_TS_TOTAL = sum(len(t) for _, t in _TREND_STATE_SUBGROUPS)
assert _TS_TOTAL == 9


# ===== PRICE_INDICATORS (6 keys — flat) =====

_GROUP_PRICE_INDICATORS = [
    ("EMA_8",                  "ema_8"),
    ("EMA_21",                 "ema_21"),
    ("SMA_50",                 "sma_50"),
    ("SMA_200",                "sma_200"),
    ("VWAP",                   "vwap"),
    ("ATR",                    "atr"),
]
assert len(_GROUP_PRICE_INDICATORS) == 6


# ===== FLOOR_ANALYSIS (4 top-level + higher_frame sub-object) =====

_GROUP_FLOOR_ANALYSIS_TOP = [
    ("Floor_Failure_Context",   "context"),
    ("Floor_Breach_Dist",       "breach_dist"),
    ("Floor_Failure_Reclaim",   "reclaim_progress"),         # SEM-001
    ("Floor_Failure_Threshold", "threshold"),
]

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


# ===== TRADE_SETUP (31 keys — 7 sub-groups) =====

_TS_TARGETS = [
    ("Profit_Target",               "level"),
    ("Profit_Target_Source",        "source"),
    ("Profit_Target_Role",          "role"),
    ("Profit_Target_Synthetic",     "synthetic"),
    ("Profit_Target_Synthetic_Note","synthetic_note"),
]

_TS_STOPS = [
    ("Hard_Stop",                   "hard"),
    ("Hard_Stop_Note",              "hard_note"),
    ("Original_Hard_Stop",          "original"),
    ("Stop_Adjusted_Flag",          "adjusted"),             # SEM-001
    ("Stop_Adjusted_Reason",        "adjusted_reason"),
    ("Structural_Floor",            "floor"),
    ("Pullback_Zone_Upper",         "pullback_zone_upper"),  # DIAG-001 Phase 2A
]

_TS_RESISTANCE = [
    ("Cons_High",                   "high"),                 # SEM-001
    ("Resistance",                  "level"),
    ("Resistance_Note",             "note"),
]

_TS_FIBONACCI = [
    ("Fib_382_Level",               "b_382"),
    ("Fib_500_Level",               "b_500"),
    ("Fib_Confluence",              "b_confluence"),
    ("Fib_A_382_Level",             "a_382"),
    ("Fib_A_500_Level",             "a_500"),
    ("Fib_A_Confluence",            "a_confluence"),
]

_TS_ROUND_NUMBERS = [
    ("RN_Target_Proximity",         "target"),               # SEM-001
    ("RN_Stop_Proximity",           "stop"),                 # SEM-001
    ("RN_Floor_Proximity",          "floor"),                # SEM-001
]

_TS_MEASURED_MOVE = [
    ("MM_Target",                   "target"),               # ENG-004
    ("MM_Rally_ATR",                "rally_atr"),            # ENG-004
]

_TS_POSITIONING = [
    ("ATR_Dist",                    "atr_distance"),          # SEM-001
    ("ATR_Dist_Anchor",             "atr_distance_anchor"),   # SEM-001
    ("ATR_Dist_Note",               "atr_distance_note"),     # SEM-001
    ("Anchor_Label",                "anchor_label"),
    ("Anchor_Type",                 "anchor_type"),
    ("Floor_Prox_Pct",              "floor_proximity_pct"),   # SEM-001
    ("Extension_Limit",             "extension_limit"),
]

_TS_EXEC_WINDOW = [
    ("Window_Limit",                "limit"),
    ("Window_Reset_Event",          "reset_event"),
]

_TRADE_SETUP_SUBGROUPS = [
    ("targets",          _TS_TARGETS),
    ("stops",            _TS_STOPS),
    ("resistance",       _TS_RESISTANCE),
    ("fibonacci",        _TS_FIBONACCI),
    ("round_numbers",    _TS_ROUND_NUMBERS),
    ("measured_move",    _TS_MEASURED_MOVE),
    ("positioning",      _TS_POSITIONING),
    ("execution_window", _TS_EXEC_WINDOW),
]

_SETUP_TOTAL = sum(len(t) for _, t in _TRADE_SETUP_SUBGROUPS)
assert _SETUP_TOTAL == 35  # ENG-004: +2 for MM_Target, MM_Rally_ATR


# ===== ENTRY_PROXIMITY (5 keys — flat) =====

_GROUP_ENTRY_PROXIMITY = [
    ("Proximity_Signal",        "signal"),
    ("Proximity_Blocking_Gate", "blocking_gate"),
    ("Proximity_Distance",      "distance"),
    ("Proximity_Target",        "target"),
    ("Proximity_Note",          "note"),
]
assert len(_GROUP_ENTRY_PROXIMITY) == 5


# ===== EXIT_SIGNALS (6 keys — flat) =====

_GROUP_EXIT_SIGNALS = [
    ("Exit_Signal",             "signal"),
    ("Exit_Triggers",           "triggers"),
    ("Exit_Reason",             "reason"),
    ("Exit_VWAP_Counter",       "vwap_counter"),
    ("Exit_EMA8_Counter",       "ema8_counter"),
    ("Established_Hourly_Low",  "established_hourly_low"),
]
assert len(_GROUP_EXIT_SIGNALS) == 6


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

    trade_snapshot = {
        "current_price":    _current_price,
        "bar_close_price":  _pe42_bar_close,        # PE-42: always the completed bar close
        "price_source":     _pe42_price_source,      # PE-42: LIVE | DAILY_CLOSE | BAR | UNAVAILABLE
        "support":          flat_metrics.get("Structural_Floor", None),
        "resistance":       flat_metrics.get("Resistance", None),
        "avg_daily_volume": flat_metrics.get("ADV_20", None),
        "classification": {
            "type":           "ETF" if is_etf else ("EQUITY" if is_etf is not None else None),
            "convexity":      flat_metrics.get("Convexity_Class", None),
            "exchange":       flat_metrics.get("ETF_Primary_Exchange", None),
            "etf_detection":  flat_metrics.get("ETF_Detection_Source", None),
        },
    }

    # --- higher_frame sub-object ---
    higher_frame = {k: None for k in _HIGHER_FRAME_ALL_KEYS}
    for flat_key, grouped_key in _HIGHER_FRAME_MAP:
        val = flat_metrics.get(flat_key)
        if val is not None:
            higher_frame[grouped_key] = val

    # --- floor_analysis with nested higher_frame ---
    floor_analysis = _map(_GROUP_FLOOR_ANALYSIS_TOP)
    floor_analysis["higher_frame"] = higher_frame

    # --- Assemble in operator reading order ---
    # PE-42: data_basis is the FIRST field, before action_summary.
    # DIAG-001 Phase 2B: action_summary next. status/diagnostic removed (DD-11).
    result = {
        "data_basis":       flat_metrics.get("Data_Basis", None),  # PE-42: transparency note
        "action_summary":   action_summary,
        "trade_snapshot":   trade_snapshot,
        "trade_quality":    _map_subgrouped(_TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS),
        "trade_risk":       _map(_GROUP_TRADE_RISK),
        "trend_state":      _map_subgrouped(_TREND_STATE_SUBGROUPS),
        "price_indicators": _map(_GROUP_PRICE_INDICATORS),
        "floor_analysis":   floor_analysis,
        "trade_setup":      _map_subgrouped(_TRADE_SETUP_SUBGROUPS),
        "entry_proximity":  _map(_GROUP_ENTRY_PROXIMITY),
        "exit_signals":     _map(_GROUP_EXIT_SIGNALS),
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
        "reason": reason,
        "action": None,
        "context": None,
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

    DIAG-001 Phase 2B: Reads from action_summary instead of status/diagnostic.
    Maps verdict back to legacy status for backward compat.
    entry_strategy extracted from action_summary, not trade_snapshot (DD-3).
    """
    _as = grouped.get("action_summary", {})
    verdict = _as.get("verdict", "ERROR")

    # Map verdict back to legacy status for backward compat
    if verdict == "VALID":
        status = "PASS"
    elif verdict == "INVALID":
        status = "HALT"
    else:
        status = "ERROR"

    # Reconstruct best-effort diagnostic from action_summary fields
    _reason = _as.get("reason", "")
    _mandate = _as.get("action", "") or ""
    _context = _as.get("context", "") or ""
    diagnostic = f"{_reason}. {_context} {_mandate}".strip()

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

    # trade_snapshot (skip support/resistance/stop_loss/target — they're duplicates)
    _unmap(grouped.get("trade_snapshot", {}), _GROUP_TRADE_SNAPSHOT_MAPPED)
    # PE-42: Reverse-map new trade_snapshot fields
    _ts = grouped.get("trade_snapshot", {})
    if "bar_close_price" in _ts:
        flat["Bar_Close_Price"] = _ts["bar_close_price"]
    if "price_source" in _ts:
        flat["Price_Source"] = _ts["price_source"]
    # classification: reverse type label back to Is_ETF boolean
    cls = grouped.get("trade_snapshot", {}).get("classification", {})
    if cls:
        type_val = cls.get("type")
        if type_val is not None:
            flat["Is_ETF"] = (type_val == "ETF")
        flat["Convexity_Class"] = cls.get("convexity")
        flat["ETF_Primary_Exchange"] = cls.get("exchange")
        flat["ETF_Detection_Source"] = cls.get("etf_detection")
    _unmap_subgrouped(grouped.get("trade_quality", {}), _TRADE_QUALITY_SUBGROUPS, _TQ_SCALARS)
    _unmap(grouped.get("trade_risk", {}), _GROUP_TRADE_RISK)
    _unmap_subgrouped(grouped.get("trend_state", {}), _TREND_STATE_SUBGROUPS)
    _unmap(grouped.get("price_indicators", {}), _GROUP_PRICE_INDICATORS)

    fa = grouped.get("floor_analysis", {})
    _unmap(fa, _GROUP_FLOOR_ANALYSIS_TOP)
    hf = fa.get("higher_frame", {})
    if hf:
        has_daily = hf.get("daily_sma50") is not None or hf.get("daily_sma50_slope") is not None
        has_weekly_rising = hf.get("sma50_rising") is not None
        if has_daily:
            for gk, fk in _HIGHER_FRAME_REVERSE_A.items():
                if gk in hf: flat[fk] = hf[gk]
        elif has_weekly_rising:
            for gk, fk in _HIGHER_FRAME_REVERSE_B.items():
                if gk in hf: flat[fk] = hf[gk]
        else:
            if any(hf.get(k) is not None for k in ("golden_cross", "price_vs_sma200", "sma200", "sma50", "sma50_slope")):
                for gk, fk in _HIGHER_FRAME_REVERSE_C.items():
                    if gk in hf: flat[fk] = hf[gk]

    _unmap_subgrouped(grouped.get("trade_setup", {}), _TRADE_SETUP_SUBGROUPS)
    _unmap(grouped.get("entry_proximity", {}), _GROUP_ENTRY_PROXIMITY)
    _unmap(grouped.get("exit_signals", {}), _GROUP_EXIT_SIGNALS)
    _unmap(grouped.get("_debug", {}), _GROUP_DEBUG)

    # DIAG-001 Phase 2B (DD-3): entry_strategy now in action_summary, not trade_snapshot.
    # Applied LAST so action_summary values take precedence over trade_setup group values.
    es = _as.get("entry_strategy")
    if es and es.get("entry_price") is not None:
        flat["Entry_Reference"] = es["entry_price"]
    if es and es.get("stop_loss") is not None:
        flat["Hard_Stop"] = es["stop_loss"]
    if es and es.get("target") is not None:
        flat["Profit_Target"] = es["target"]

    # DIAG-001 Amendment: existing_position_exit_signal / existing_position_exit_reason on INVALID paths.
    # Maps to new flat keys — does NOT overwrite Exit_Signal / Exit_Reason from exit_signals group.
    if _as.get("existing_position_exit_signal") is not None:
        flat["Exit_Signal_Active"] = _as["existing_position_exit_signal"]
    if _as.get("existing_position_exit_reason") is not None and _as["existing_position_exit_signal"]:
        flat["Exit_Reason_Summary"] = _as["existing_position_exit_reason"]

    return status, diagnostic, flat


# ---------------------------------------------------------------------------
# Key coverage audit
# ---------------------------------------------------------------------------

def _audit_key_coverage(flat_metrics: dict) -> list:
    unmapped = set(flat_metrics.keys()) - MAPPED_FLAT_KEYS
    unmapped.discard("df_ctx")
    unmapped.discard("metrics")
    return sorted(unmapped)

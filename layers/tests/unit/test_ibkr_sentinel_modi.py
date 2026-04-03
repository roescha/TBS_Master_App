"""
MOD-I Unit Test Harness -- Market Breadth Sentinel Enhancement
Covers TC-01 through TC-15 from MODI_Market_Breadth_Sentinel_Spec_v1_0

Run: python test_modi_breadth.py
No IBKR connection required. All data is synthetic.
"""

import sys
import pandas as pd
from io import StringIO

# ============================================================
# EXTRACT: _compute_breadth (verbatim from ibkr_sentinel.py)
# Standalone copy for unit testing without IBKR dependency.
# If the sentinel function changes, this copy must be updated.
# ============================================================

def _linear_slope(values):
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def _compute_breadth(df_spy_daily, df_rsp_daily, regime_str):
    """
    Compute RSP/SPY breadth divergence.
    Returns dict with 6 fields per spec Section 7.1.
    """
    _unavailable = {
        "rsp_close": None,
        "rsp_spy_ratio": None,
        "rsp_spy_ratio_sma20": None,
        "rsp_spy_slope_5d": None,
        "breadth_status": "UNAVAILABLE",
        "breadth_persistence": 0,
    }

    # Guard: RSP fetch failure or insufficient bars
    if df_rsp_daily is None or len(df_rsp_daily) < 30:
        return _unavailable

    # Align RSP and SPY by date (inner join)
    df_spy_tmp = df_spy_daily[["date", "close"]].copy()
    df_rsp_tmp = df_rsp_daily[["date", "close"]].copy()
    df_spy_tmp = df_spy_tmp.rename(columns={"close": "spy_close"})
    df_rsp_tmp = df_rsp_tmp.rename(columns={"close": "rsp_close"})
    aligned = pd.merge(df_spy_tmp, df_rsp_tmp, on="date", how="inner")

    if len(aligned) < 25:
        return _unavailable

    # Compute ratio series
    aligned["ratio"] = aligned["rsp_close"] / aligned["spy_close"]

    # 20-bar SMA of ratio
    aligned["ratio_sma_20"] = aligned["ratio"].rolling(window=20).mean()

    # 5-day linear slope (manual least-squares, no numpy)
    aligned["ratio_slope_5d"] = aligned["ratio"].rolling(window=5).apply(
        lambda x: _linear_slope(list(x)), raw=False
    )

    # Latest values for output
    latest = aligned.iloc[-1]
    rsp_close_val = float(latest["rsp_close"])
    ratio_val = float(latest["ratio"])
    sma20_val = float(latest["ratio_sma_20"]) if not pd.isna(latest["ratio_sma_20"]) else None
    slope_val = float(latest["ratio_slope_5d"]) if not pd.isna(latest["ratio_slope_5d"]) else None

    if sma20_val is None or slope_val is None:
        return _unavailable

    # Regime eligibility: only GREEN regimes (BULLISH or DEFENSIVE)
    eligible = ("BULLISH" in regime_str or "DEFENSIVE" in regime_str)
    if not eligible:
        return {
            "rsp_close": rsp_close_val,
            "rsp_spy_ratio": ratio_val,
            "rsp_spy_ratio_sma20": sma20_val,
            "rsp_spy_slope_5d": slope_val,
            "breadth_status": "SUPPRESSED",
            "breadth_persistence": 0,
        }

    # Persistence: evaluate divergence condition on each of the last N bars
    # Count consecutive qualifying bars from most recent backward
    persistence = 0
    n_bars = min(len(aligned), 20)  # reasonable lookback cap
    for offset in range(n_bars):
        idx = len(aligned) - 1 - offset
        if idx < 0:
            break
        bar_slope = aligned["ratio_slope_5d"].iloc[idx]
        bar_ratio = aligned["ratio"].iloc[idx]
        bar_sma = aligned["ratio_sma_20"].iloc[idx]
        if pd.isna(bar_slope) or pd.isna(bar_sma):
            break
        if float(bar_slope) < 0 and float(bar_ratio) < float(bar_sma):
            persistence += 1
        else:
            break

    breadth_status = "DIVERGENCE" if persistence >= 3 else "CONFIRMING"

    return {
        "rsp_close": rsp_close_val,
        "rsp_spy_ratio": ratio_val,
        "rsp_spy_ratio_sma20": sma20_val,
        "rsp_spy_slope_5d": slope_val,
        "breadth_status": breadth_status,
        "breadth_persistence": persistence,
    }


# ============================================================
# DATA FACTORIES
# ============================================================

def _make_dates(n):
    """Generate n business days ending today-ish."""
    return pd.bdate_range(end="2026-04-02", periods=n).strftime("%Y%m%d").tolist()


def _make_spy(n=60, base=550.0, trend=0.0):
    """
    Build a synthetic SPY daily DataFrame.
    base: starting close price
    trend: daily drift (positive = rising)
    """
    dates = _make_dates(n)
    closes = [base + trend * i for i in range(n)]
    return pd.DataFrame({
        "date": dates,
        "close": closes,
    })


def _make_rsp(n=60, base=160.0, trend=0.0, diverge_start=None, diverge_drift=-0.15):
    """
    Build a synthetic RSP daily DataFrame.
    diverge_start: bar index where RSP starts diverging (declining faster)
    diverge_drift: additional daily drift applied from diverge_start onward
    """
    dates = _make_dates(n)
    closes = []
    for i in range(n):
        val = base + trend * i
        if diverge_start is not None and i >= diverge_start:
            val += diverge_drift * (i - diverge_start)
        closes.append(val)
    return pd.DataFrame({
        "date": dates,
        "close": closes,
    })


def _make_diverging_pair(n=60, diverge_days=5):
    """
    Create SPY + RSP pair where RSP diverges for the last diverge_days bars.
    SPY is flat/rising. RSP starts declining relative to SPY.
    The ratio initially sits above its SMA20 then drops below.
    """
    spy = _make_spy(n=n, base=550.0, trend=0.3)
    # RSP tracks SPY proportionally for first part, then diverges
    rsp_closes = []
    dates = _make_dates(n)
    for i in range(n):
        spy_c = 550.0 + 0.3 * i
        ratio = 0.295  # base ratio
        if i >= (n - diverge_days):
            # Accelerating decline in last diverge_days bars
            days_into_diverge = i - (n - diverge_days)
            ratio -= 0.002 * (days_into_diverge + 1)
        rsp_closes.append(spy_c * ratio)

    rsp = pd.DataFrame({"date": dates, "close": rsp_closes})
    return spy, rsp


def _make_stable_pair(n=60):
    """SPY + RSP with stable ratio (no divergence)."""
    spy = _make_spy(n=n, base=550.0, trend=0.3)
    dates = _make_dates(n)
    rsp_closes = [(550.0 + 0.3 * i) * 0.295 for i in range(n)]
    rsp = pd.DataFrame({"date": dates, "close": rsp_closes})
    return spy, rsp


# ============================================================
# ORCHESTRATOR DISPLAY LOGIC (extracted for testing)
# ============================================================

def render_breadth_oneliner(sentinel_details):
    """Reproduce the orchestrator one-liner breadth segment."""
    _breadth = sentinel_details.get("breadth_status") if sentinel_details else None
    if _breadth == "DIVERGENCE":
        return " | Breadth: DIVERGENCE [!]"
    elif _breadth == "CONFIRMING":
        return " | Breadth: CONFIRMING"
    return ""


def render_breadth_expanded(sentinel_details):
    """Reproduce the orchestrator expanded breadth block."""
    lines = []
    _breadth = sentinel_details.get("breadth_status") if sentinel_details else None
    if _breadth == "DIVERGENCE":
        _slope = sentinel_details.get("rsp_spy_slope_5d") or 0
        _ratio = sentinel_details.get("rsp_spy_ratio") or 0
        _sma = sentinel_details.get("rsp_spy_ratio_sma20") or 0
        lines.append(
            "   BREADTH: DIVERGENCE [!] RSP/SPY ratio declining "
            "(5d slope: %.4f, ratio: %.3f, SMA20: %.3f)" % (_slope, _ratio, _sma)
        )
        lines.append(
            "   Equal-weight index underperforming cap-weight. "
            "Advance may be narrowing to mega-cap leadership."
        )
    elif _breadth == "CONFIRMING":
        _slope = sentinel_details.get("rsp_spy_slope_5d") or 0
        lines.append(
            "   BREADTH: CONFIRMING (RSP/SPY ratio stable, 5d slope: %+.4f)" % _slope
        )
    return lines


def render_breadth_threats(sentinel_details):
    """Reproduce the orchestrator threats entry for breadth."""
    _breadth = sentinel_details.get("breadth_status") if sentinel_details else None
    if _breadth == "DIVERGENCE":
        return "BREADTH DIVERGENCE: RSP/SPY ratio declining -- advance may be narrowing"
    return None


# ============================================================
# TEST RUNNER
# ============================================================

_pass_count = 0
_fail_count = 0


def assert_eq(test_id, field, actual, expected):
    global _pass_count, _fail_count
    if actual == expected:
        _pass_count += 1
    else:
        _fail_count += 1
        print(f"  FAIL  {test_id} | {field}: expected {expected!r}, got {actual!r}")


def assert_not_none(test_id, field, actual):
    global _pass_count, _fail_count
    if actual is not None:
        _pass_count += 1
    else:
        _fail_count += 1
        print(f"  FAIL  {test_id} | {field}: expected not None, got None")


def assert_is_none(test_id, field, actual):
    global _pass_count, _fail_count
    if actual is None:
        _pass_count += 1
    else:
        _fail_count += 1
        print(f"  FAIL  {test_id} | {field}: expected None, got {actual!r}")


def assert_true(test_id, field, condition):
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
    else:
        _fail_count += 1
        print(f"  FAIL  {test_id} | {field}: condition is False")


def assert_contains(test_id, field, haystack, needle):
    global _pass_count, _fail_count
    if needle in haystack:
        _pass_count += 1
    else:
        _fail_count += 1
        print(f"  FAIL  {test_id} | {field}: '{needle}' not found in '{haystack}'")


# ============================================================
# 10.1 CORE DIVERGENCE DETECTION (TC-01 through TC-05)
# ============================================================

def test_tc01():
    """TC-01: GREEN regime, slope < 0, ratio < SMA20, 3+ consecutive days -> DIVERGENCE"""
    print("TC-01: DIVERGENCE fires with 3+ consecutive days...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    assert_eq("TC-01", "breadth_status", result["breadth_status"], "DIVERGENCE")
    assert_true("TC-01", "breadth_persistence >= 3", result["breadth_persistence"] >= 3)
    assert_not_none("TC-01", "rsp_close", result["rsp_close"])
    assert_not_none("TC-01", "rsp_spy_ratio", result["rsp_spy_ratio"])
    assert_not_none("TC-01", "rsp_spy_ratio_sma20", result["rsp_spy_ratio_sma20"])
    assert_true("TC-01", "slope < 0", result["rsp_spy_slope_5d"] < 0)
    assert_true("TC-01", "ratio < sma20",
                result["rsp_spy_ratio"] < result["rsp_spy_ratio_sma20"])
    # Orchestrator threats entry
    threat = render_breadth_threats(result)
    assert_eq("TC-01", "threats entry present", threat is not None, True)
    assert_contains("TC-01", "threats text", threat, "BREADTH DIVERGENCE")
    # Orchestrator one-liner
    oneliner = render_breadth_oneliner(result)
    assert_contains("TC-01", "oneliner DIVERGENCE", oneliner, "DIVERGENCE [!]")
    # Expanded block
    expanded = render_breadth_expanded(result)
    assert_true("TC-01", "expanded block lines >= 2", len(expanded) >= 2)


def test_tc02():
    """TC-02: GREEN regime, slope < 0, ratio < SMA20, only 2 consecutive days -> CONFIRMING"""
    print("TC-02: CONFIRMING when only 2 consecutive days...")
    # Explicitly construct data where only the last 2 bars satisfy the
    # divergence condition (slope < 0 AND ratio < SMA20).
    # The bar before those 2 has ratio ABOVE SMA20, breaking the streak.
    n = 60
    spy = _make_spy(n=n, base=550.0, trend=0.3)
    dates = _make_dates(n)
    rsp_closes = []
    for i in range(n):
        spy_c = 550.0 + 0.3 * i
        if i < (n - 2):
            # Flat stable ratio well above where SMA20 will be
            ratio = 0.295
        else:
            # Sharp drop in last 2 bars only -- ratio drops below SMA20
            days_into = i - (n - 2)
            ratio = 0.295 - 0.004 * (days_into + 1)
        rsp_closes.append(spy_c * ratio)
    rsp = pd.DataFrame({"date": dates, "close": rsp_closes})

    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    assert_true("TC-02", "breadth_persistence < 3", result["breadth_persistence"] < 3)
    assert_eq("TC-02", "breadth_status", result["breadth_status"], "CONFIRMING")
    # No threats entry
    threat = render_breadth_threats(result)
    assert_eq("TC-02", "no threats entry", threat, None)


def test_tc03():
    """TC-03: GREEN regime, slope < 0, ratio >= SMA20 -> CONFIRMING"""
    print("TC-03: CONFIRMING when slope negative but ratio above SMA20...")
    # Build pair where RSP declines slightly but ratio stays above SMA20
    # Use stable pair with a tiny recent dip (not enough to cross below SMA)
    spy = _make_spy(n=60, base=550.0, trend=0.3)
    dates = _make_dates(60)
    # Ratio starts at 0.295, gently rises to 0.298, then dips to 0.296
    # (still above the SMA20 which will be around 0.296-0.297)
    rsp_closes = []
    for i in range(60):
        spy_c = 550.0 + 0.3 * i
        if i < 55:
            ratio = 0.295 + 0.0001 * i  # slow rise
        else:
            ratio = 0.295 + 0.0001 * 55 - 0.0002 * (i - 55)  # tiny dip
        rsp_closes.append(spy_c * ratio)
    rsp = pd.DataFrame({"date": dates, "close": rsp_closes})

    result = _compute_breadth(spy, rsp, "DEFENSIVE (Yellow)")
    # Slope may be slightly negative from the tiny dip, but ratio should be
    # above or very close to SMA20. Either way, persistence should be < 3.
    assert_eq("TC-03", "breadth_status", result["breadth_status"], "CONFIRMING")


def test_tc04():
    """TC-04: GREEN regime, slope >= 0, ratio < SMA20 -> CONFIRMING"""
    print("TC-04: CONFIRMING when ratio below SMA but slope not negative...")
    spy = _make_spy(n=60, base=550.0, trend=0.3)
    dates = _make_dates(60)
    # Ratio drops below SMA20 early, then starts recovering (slope positive)
    rsp_closes = []
    for i in range(60):
        spy_c = 550.0 + 0.3 * i
        if i < 40:
            ratio = 0.296
        elif i < 50:
            ratio = 0.290  # drop below SMA
        else:
            ratio = 0.290 + 0.0005 * (i - 50)  # recovering (positive slope)
        rsp_closes.append(spy_c * ratio)
    rsp = pd.DataFrame({"date": dates, "close": rsp_closes})

    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    # The latest bars have positive slope (recovery), so divergence condition
    # (slope < 0) fails even if ratio is below SMA.
    assert_eq("TC-04", "breadth_status", result["breadth_status"], "CONFIRMING")
    assert_true("TC-04", "persistence < 3", result["breadth_persistence"] < 3)


def test_tc05():
    """TC-05: GREEN regime, slope >= 0, ratio >= SMA20 -> CONFIRMING"""
    print("TC-05: CONFIRMING when all clear (slope positive, ratio above SMA)...")
    spy, rsp = _make_stable_pair(n=60)
    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    assert_eq("TC-05", "breadth_status", result["breadth_status"], "CONFIRMING")
    assert_eq("TC-05", "breadth_persistence", result["breadth_persistence"], 0)


# ============================================================
# 10.2 REGIME SUPPRESSION (TC-06 through TC-09)
# ============================================================

def test_tc06():
    """TC-06: RESTRICTED (Red) regime, divergence conditions met -> SUPPRESSED"""
    print("TC-06: SUPPRESSED on RESTRICTED regime...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "RESTRICTED (Red)")
    assert_eq("TC-06", "breadth_status", result["breadth_status"], "SUPPRESSED")
    assert_eq("TC-06", "breadth_persistence", result["breadth_persistence"], 0)
    assert_not_none("TC-06", "rsp_close", result["rsp_close"])
    assert_not_none("TC-06", "rsp_spy_ratio", result["rsp_spy_ratio"])


def test_tc07():
    """TC-07: SHOCK (Grey) regime, divergence conditions met -> SUPPRESSED"""
    print("TC-07: SUPPRESSED on SHOCK regime...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "SHOCK (Grey)")
    assert_eq("TC-07", "breadth_status", result["breadth_status"], "SUPPRESSED")
    assert_eq("TC-07", "breadth_persistence", result["breadth_persistence"], 0)


def test_tc08():
    """TC-08: HIGH RISK (Black) regime -> SUPPRESSED"""
    print("TC-08: SUPPRESSED on HIGH RISK regime...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "HIGH RISK (Black)")
    assert_eq("TC-08", "breadth_status", result["breadth_status"], "SUPPRESSED")


def test_tc09():
    """TC-09: AMBIGUOUS (Buffer) / UNCONFIRMED (Flicker) -> SUPPRESSED"""
    print("TC-09: SUPPRESSED on AMBIGUOUS and UNCONFIRMED regimes...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result_amb = _compute_breadth(spy, rsp, "AMBIGUOUS (Buffer)")
    result_unc = _compute_breadth(spy, rsp, "UNCONFIRMED (Flicker)")
    assert_eq("TC-09a", "breadth_status AMBIGUOUS", result_amb["breadth_status"], "SUPPRESSED")
    assert_eq("TC-09b", "breadth_status UNCONFIRMED", result_unc["breadth_status"], "SUPPRESSED")


# ============================================================
# 10.3 GRACEFUL DEGRADATION (TC-10 through TC-12)
# ============================================================

def test_tc10():
    """TC-10: RSP reqHistoricalData returns None -> UNAVAILABLE"""
    print("TC-10: UNAVAILABLE on RSP fetch failure (None)...")
    spy = _make_spy(n=60)
    result = _compute_breadth(spy, None, "BULLISH (Blue)")
    assert_eq("TC-10", "breadth_status", result["breadth_status"], "UNAVAILABLE")
    assert_is_none("TC-10", "rsp_close", result["rsp_close"])
    assert_is_none("TC-10", "rsp_spy_ratio", result["rsp_spy_ratio"])
    assert_is_none("TC-10", "rsp_spy_ratio_sma20", result["rsp_spy_ratio_sma20"])
    assert_is_none("TC-10", "rsp_spy_slope_5d", result["rsp_spy_slope_5d"])
    assert_eq("TC-10", "breadth_persistence", result["breadth_persistence"], 0)


def test_tc11():
    """TC-11: RSP returns < 30 bars -> UNAVAILABLE"""
    print("TC-11: UNAVAILABLE on insufficient RSP bars (< 30)...")
    spy = _make_spy(n=60)
    rsp_short = _make_rsp(n=20)  # only 20 bars
    result = _compute_breadth(spy, rsp_short, "BULLISH (Blue)")
    assert_eq("TC-11", "breadth_status", result["breadth_status"], "UNAVAILABLE")
    assert_is_none("TC-11", "rsp_close", result["rsp_close"])


def test_tc12():
    """TC-12: RSP and SPY date alignment mismatch -> inner join handles, no crash"""
    print("TC-12: Date alignment mismatch handled via inner join...")
    # SPY has 60 bars, RSP has 45 bars with different start date
    spy = _make_spy(n=60, base=550.0, trend=0.3)
    dates_rsp = _make_dates(45)  # shorter, overlaps with end of SPY
    rsp_closes = [(550.0 + 0.3 * (60 - 45 + i)) * 0.295 for i in range(45)]
    rsp = pd.DataFrame({"date": dates_rsp, "close": rsp_closes})

    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    # Should compute without crash. Status depends on aligned bar count.
    assert_true("TC-12", "no crash (status is valid)",
                result["breadth_status"] in ("CONFIRMING", "DIVERGENCE", "UNAVAILABLE"))


# ============================================================
# 10.4 ORCHESTRATOR DISPLAY (TC-13 through TC-15)
# ============================================================

def test_tc13():
    """TC-13: breadth_status = DIVERGENCE -> oneliner + expanded + threats"""
    print("TC-13: Orchestrator DIVERGENCE display...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    # Force DIVERGENCE if synthetic data didn't quite trigger
    # (this TC tests orchestrator rendering, not computation)
    if result["breadth_status"] != "DIVERGENCE":
        result["breadth_status"] = "DIVERGENCE"
        result["breadth_persistence"] = 5

    # One-liner
    oneliner = render_breadth_oneliner(result)
    assert_contains("TC-13", "oneliner", oneliner, "Breadth: DIVERGENCE [!]")

    # Expanded block
    expanded = render_breadth_expanded(result)
    assert_true("TC-13", "expanded has 2 lines", len(expanded) == 2)
    assert_contains("TC-13", "expanded line 1", expanded[0], "DIVERGENCE [!]")
    assert_contains("TC-13", "expanded line 1 slope", expanded[0], "5d slope:")
    assert_contains("TC-13", "expanded line 1 ratio", expanded[0], "ratio:")
    assert_contains("TC-13", "expanded line 1 SMA20", expanded[0], "SMA20:")
    assert_contains("TC-13", "expanded line 2 narrative", expanded[1], "mega-cap leadership")

    # Threats entry
    threat = render_breadth_threats(result)
    assert_eq("TC-13", "threat present", threat is not None, True)
    assert_contains("TC-13", "threat text", threat, "BREADTH DIVERGENCE")
    assert_contains("TC-13", "threat text", threat, "advance may be narrowing")

    # ASCII compliance
    for line in expanded:
        for ch in line:
            assert_true("TC-13", f"ASCII char ord={ord(ch)}", ord(ch) < 128)


def test_tc14():
    """TC-14: breadth_status = CONFIRMING, regime GREEN -> oneliner + single line, no threats"""
    print("TC-14: Orchestrator CONFIRMING display...")
    spy, rsp = _make_stable_pair(n=60)
    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")

    # One-liner
    oneliner = render_breadth_oneliner(result)
    assert_contains("TC-14", "oneliner", oneliner, "Breadth: CONFIRMING")
    assert_true("TC-14", "no DIVERGENCE in oneliner", "DIVERGENCE" not in oneliner)

    # Expanded block (single confirming line)
    expanded = render_breadth_expanded(result)
    assert_true("TC-14", "expanded has 1 line", len(expanded) == 1)
    assert_contains("TC-14", "expanded line", expanded[0], "CONFIRMING")
    assert_contains("TC-14", "expanded slope", expanded[0], "5d slope:")

    # No threats
    threat = render_breadth_threats(result)
    assert_eq("TC-14", "no threats entry", threat, None)


def test_tc15():
    """TC-15: breadth_status = SUPPRESSED or UNAVAILABLE -> nothing on dashboard"""
    print("TC-15: SUPPRESSED/UNAVAILABLE omitted from dashboard...")

    # SUPPRESSED
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result_sup = _compute_breadth(spy, rsp, "RESTRICTED (Red)")

    oneliner_sup = render_breadth_oneliner(result_sup)
    assert_eq("TC-15a", "oneliner empty (SUPPRESSED)", oneliner_sup, "")
    expanded_sup = render_breadth_expanded(result_sup)
    assert_eq("TC-15a", "expanded empty (SUPPRESSED)", len(expanded_sup), 0)
    threat_sup = render_breadth_threats(result_sup)
    assert_eq("TC-15a", "no threats (SUPPRESSED)", threat_sup, None)

    # UNAVAILABLE
    spy2 = _make_spy(n=60)
    result_una = _compute_breadth(spy2, None, "BULLISH (Blue)")

    oneliner_una = render_breadth_oneliner(result_una)
    assert_eq("TC-15b", "oneliner empty (UNAVAILABLE)", oneliner_una, "")
    expanded_una = render_breadth_expanded(result_una)
    assert_eq("TC-15b", "expanded empty (UNAVAILABLE)", len(expanded_una), 0)
    threat_una = render_breadth_threats(result_una)
    assert_eq("TC-15b", "no threats (UNAVAILABLE)", threat_una, None)


# ============================================================
# SCHEMA VALIDATION (cross-cuts all TCs)
# ============================================================

def test_schema():
    """Verify all 6 fields present in every return path."""
    print("SCHEMA: Verifying 6 fields present in all return paths...")
    required_fields = [
        "rsp_close", "rsp_spy_ratio", "rsp_spy_ratio_sma20",
        "rsp_spy_slope_5d", "breadth_status", "breadth_persistence",
    ]

    # Path 1: DIVERGENCE
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    r1 = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    for f in required_fields:
        assert_true("SCHEMA-P1", f"field '{f}' present", f in r1)

    # Path 2: CONFIRMING
    spy2, rsp2 = _make_stable_pair(n=60)
    r2 = _compute_breadth(spy2, rsp2, "BULLISH (Blue)")
    for f in required_fields:
        assert_true("SCHEMA-P2", f"field '{f}' present", f in r2)

    # Path 3: SUPPRESSED
    r3 = _compute_breadth(spy, rsp, "RESTRICTED (Red)")
    for f in required_fields:
        assert_true("SCHEMA-P3", f"field '{f}' present", f in r3)

    # Path 4: UNAVAILABLE (None RSP)
    r4 = _compute_breadth(spy, None, "BULLISH (Blue)")
    for f in required_fields:
        assert_true("SCHEMA-P4", f"field '{f}' present", f in r4)

    # Path 5: UNAVAILABLE (short RSP)
    r5 = _compute_breadth(spy, _make_rsp(n=15), "BULLISH (Blue)")
    for f in required_fields:
        assert_true("SCHEMA-P5", f"field '{f}' present", f in r5)


# ============================================================
# VOCABULARY CONSTRAINT CHECK
# ============================================================

def test_vocabulary():
    """Verify no forbidden vocabulary in breadth outputs."""
    print("VOCAB: Checking vocabulary constraints...")
    forbidden_statuses = {"GREEN", "YELLOW", "RED", "BLACK",
                          "PASS", "HALT", "REJECT", "FORCE HARVEST"}

    all_results = []
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    all_results.append(_compute_breadth(spy, rsp, "BULLISH (Blue)"))
    all_results.append(_compute_breadth(spy, rsp, "RESTRICTED (Red)"))
    all_results.append(_compute_breadth(spy, None, "BULLISH (Blue)"))

    spy2, rsp2 = _make_stable_pair(n=60)
    all_results.append(_compute_breadth(spy2, rsp2, "BULLISH (Blue)"))

    for r in all_results:
        status = r["breadth_status"]
        assert_true("VOCAB", f"'{status}' not in forbidden set",
                    status not in forbidden_statuses)
        assert_true("VOCAB", f"'{status}' in permitted set",
                    status in {"CONFIRMING", "DIVERGENCE", "SUPPRESSED", "UNAVAILABLE"})


# ============================================================
# INVARIANT: REGIME/VERDICT UNAFFECTED
# ============================================================

def test_no_regime_modification():
    """Verify _compute_breadth returns no regime/verdict fields."""
    print("INVARIANT: No regime/verdict in breadth output...")
    spy, rsp = _make_diverging_pair(n=60, diverge_days=8)
    result = _compute_breadth(spy, rsp, "BULLISH (Blue)")
    assert_true("INVARIANT", "no 'regime' key", "regime" not in result)
    assert_true("INVARIANT", "no 'verdict' key", "verdict" not in result)
    assert_true("INVARIANT", "no 'reason' key", "reason" not in result)
    assert_true("INVARIANT", "no 'storm_watch' key", "storm_watch" not in result)


# ============================================================
# LINEAR SLOPE UNIT TEST
# ============================================================

def test_linear_slope():
    """Verify the manual least-squares slope function."""
    print("SLOPE: Verifying _linear_slope correctness...")
    # Perfectly rising: [1, 2, 3, 4, 5] -> slope = 1.0
    assert_true("SLOPE", "rising slope = 1.0", abs(_linear_slope([1, 2, 3, 4, 5]) - 1.0) < 1e-9)
    # Perfectly flat: [3, 3, 3, 3, 3] -> slope = 0.0
    assert_true("SLOPE", "flat slope = 0.0", abs(_linear_slope([3, 3, 3, 3, 3]) - 0.0) < 1e-9)
    # Perfectly falling: [5, 4, 3, 2, 1] -> slope = -1.0
    assert_true("SLOPE", "falling slope = -1.0", abs(_linear_slope([5, 4, 3, 2, 1]) - (-1.0)) < 1e-9)
    # Single value: [7] -> slope = 0.0
    assert_true("SLOPE", "single value = 0.0", abs(_linear_slope([7]) - 0.0) < 1e-9)
    # Two values: [1, 3] -> slope = 2.0
    assert_true("SLOPE", "two values slope = 2.0", abs(_linear_slope([1, 3]) - 2.0) < 1e-9)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 72)
    print("MOD-I UNIT TEST HARNESS -- TC-01 through TC-15 + extras")
    print("=" * 72)
    print()

    tests = [
        # 10.1 Core Divergence Detection
        test_tc01,
        test_tc02,
        test_tc03,
        test_tc04,
        test_tc05,
        # 10.2 Regime Suppression
        test_tc06,
        test_tc07,
        test_tc08,
        test_tc09,
        # 10.3 Graceful Degradation
        test_tc10,
        test_tc11,
        test_tc12,
        # 10.4 Orchestrator Display
        test_tc13,
        test_tc14,
        test_tc15,
        # Cross-cutting
        test_schema,
        test_vocabulary,
        test_no_regime_modification,
        test_linear_slope,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            _fail_count += 1
            print(f"  CRASH {t.__name__}: {e}")

    print()
    print("=" * 72)
    total = _pass_count + _fail_count
    print(f"RESULT: {_pass_count} PASS / {_fail_count} FAIL / {total} TOTAL")
    if _fail_count == 0:
        print("ALL TESTS PASSED")
    else:
        print("FAILURES DETECTED -- review above")
    print("=" * 72)

    sys.exit(0 if _fail_count == 0 else 1)

import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
# TBS PURITY ENGINE (Layer 2) v8.6
# CONVEXITY INTEGRATION: Option B (Minimum Viable C-3)
# Implements: Redesign Proposal §6.2, Execution Map §VI (Phase 1 + Phase 2)
#   CVX-1: convexity_class parameter + input validation
#   CVX-2: Convexity_Class tag in metrics payload
#   CVX-3: Modifier D → INFORMATIONAL for C-3
#   CVX-4: Profit_Target_Synthetic suppression for C-3
#   CVX-5: Profit_Target_Role field (PRESCRIPTIVE / INFORMATIONAL)
#   CVX-6: Risk_Per_Unit metric (C-3 RESOLVING: (price − EMA 8) / ATR)
#   CVX-7: EMA 8 EXIT escalation (WARNING → EXIT for C-3)
#   CVX-8: Profile B Expectancy bypass (R:R against fixed resistance suppressed for C-3)
# Backward compatible: convexity_class=None produces identical output to v8.6.
# Bug fixes: PE-1 (NYSE retry gated on USD currency)
#            PE-2 (Engine_State label: distinguish ADX<20 from MA Squeeze; PE-2b: ADX<20 takes priority when both true)
#            PE-3 (LSE ETFs: add VANG keyword + LSEETF exchange detection; override price_scaler to 1.0)
#            PE-4 (LSE ETF liquidity threshold: $5M instead of $50M -- market-maker backed, low on-exchange vol)
#            PE-5 (Profile input validation: reject unrecognised profiles instead of silent TREND default)
#            PE-7 (Suppress R:R metrics when Exit_Signal active -- no entry metrics when floor is broken)
#            PE-9 (Profile A bar-close cadence: ADX, DI, Squeeze must read last COMPLETED bar, not live stub)
#            PE-9b (Exit signal decoupling: Profile A §X exit uses strict close < VWAP counter, no §4.1 grace buffer)
#            PE-10 (Null Profit_Target when price below floor -- target without ratio is a payload contradiction)
#            PE-11 (Extension warning annotation on MID-RANGE HALT -- prevents masked dual-block surprise)
#            PE-12 (Round actual_price in Reward_Risk_Note -- prevents floating point display leak on GBP stocks)
#            PE-13 (Override target = Resistance with R:R >= 0.5 gate -- Floor+1.5ATR is always below price in established trends)
#            PE-14 (Focus chart Consolidation Range hlines used price_scaler division -- 1/100 offset on GBP pence-denominated axes)
#            PE-15 (Floor Violation Pre-Check diagnostic hardcoded GBP÷100 instead of price_scaler -- wrong display for LSE ETFs)
#            PE-16 (Focus Chart 10-bar window off-by-one for Profile A -- chart used iloc[-11:-1] while engine uses iloc[-12:-2])
#            PE-17 (Doc 2 §VIII.2 updated: Override target = Resistance, not Floor+1.5 ATR -- code unchanged, doc aligned)
#            PE-18 (Existence guard for ATRr_14 column -- merged into PE-24 unified guard block)
#            PE-19 (NaN guard on ADX/DI values -- NaN ADX silently bypassed MID-RANGE gate via NumPy NaN<20→False)
#            PE-20 (Context Chart missing Volume SMA 9 overlay -- added computation + trace for HITL climax detection)
#            PE-21 (Breakout PASS diagnostic displayed "resistance None" -- suppressed metrics value used instead of resistance_raw)
#            PE-22 (RESOLVING HALT diagnostic displayed "at None" -- same root cause as PE-21, Convex Support edge case)
#            PE-23 (SMA_200 NaN serialization guard -- Profile A short-history tickers crashed json.dumps with NaN literal)
#            PE-24 (Unified existence guard for ATRr_14, vol_sma_9, vol_sma_20 -- subsumes PE-18)
#            PE-25 (Exit_Signal false on FLOOR FAILURE + single reclaim bar -- override ensures structural break persists)
#            PE-25b (3-Bar Reclaim Mandate: floor failure requires 3 consecutive closes above floor to reset Exit_Signal)
#            R-1  (Pre-check bar index aligned to Profile A i0=-2 offset -- was shifted by 1 bar vs main check)
#            R-2  (Design note: grace buffer asymmetry between entry/exit counters is intentional per §X vs §4.1)
#            R-3  (Exit counter lookback depth: range(0,4) -> range(0,5) to match entry counter depth)
#            R-4  (ATR_Dist_Note reworded: no longer asserts Exit_Signal state, defers to field)
#            R-5  (Comment: PE-7 suppression dependency on PE-25 for correct Exit_Signal)
#            R-6  (Directional Dominance gate widened to universal scope -- all profiles now evaluated; exemptions preserved inside)
#            R-7  (Floor Proximity Audit deduplication -- gate blocks reference pre-computed floor_prox_pct, removing redundant recomputation)
#            PE-26 (Standardised Profit Target naming: Target_1 -> Profit_Target_Synthetic; RR_Target_Price -> Profit_Target; Cons_High_Source -> Profit_Target_Source; unified across all profiles)
#            R-8  (Retire Stop_Value legacy key -- was always identical to Hard_Stop, dead payload duplication)
#            R-9  (Surface Extension_Limit in metrics -- operator sees ATR_Dist but not the threshold)
#            R-10 (Surface Window_Limit in metrics -- operator sees window_count but not the max)
#            PE-27 (Surface Established_Hourly_Low in Profile A metrics + Exit_VWAP_Counter)
#            PE-28 (Graduate Exit_Signal: false/"WARNING"/"EXIT". WARNING=single trigger, EXIT=structural. Metric suppression only on EXIT)
#            PE-28b (Fix: PE-25b backward scan pre-check blocks were bypassing PE-28 graduation -- still setting boolean True. Now uses "EXIT" + Exit_Triggers)
#            PE-29 (Scale floor failure threshold by profile: A=8 hourly bars, B/C=4. Prevents routine intraday pullbacks from triggering structural break on hourly profiles)
# Features:  TQ-1 (Trend Quality Score: ADX Slope Acceleration + Volume Trend Confirmation Ratio)
#            TQ-2 (Trend Quality Override: Operator discretion on EXTENDED assets under mandatory risk reduction)
# PE-CAL-1b: Profile C TQ Override ceiling 1.0→2.0 ATR (was dead code: base=1.0, ceil=1.0 made override permanently ineligible)
# PE-CAL-2:  Profile A Expectancy Gate floor-proximity fix. When risk < 20% ATR, substitute hard stop as R:R denominator.
#            Previously: degenerate R:R (9999) passed the 1:2 gate while diagnostic flagged the number as meaningless.
#            Now: hard-stop R:R enforced. If reward / hard-stop risk < 2.0, HALT. Realistic R:R displayed in all cases.
# PE-7b:    PE-7 block relocated from after Expectancy Gate to after Bug #33 (pre-PHASE 1.5).
#            Fires before Pre-Check early returns, preventing R:R/Profit_Target leak on EXIT.
#            Profile A guard added after Expectancy Gate to prevent re-population on VWAP EXIT.
#            Follows same relocation pattern as Bug #33 (Profit_Target_Synthetic).
# R-11:     Gate reorder to match Doc 2 §V tier hierarchy. Previously: Extension (Tier 3) ran
#            before DI/Modifiers/Window (Tier 2). Now: Tier 2 (Gates 4.1-4.3) fires before
#            Tier 3 (Gates 5-5.6). Zero behavioural change (all gates are independent HALTs
#            with no data dependencies). Diagnostic priority now matches document authority.
# CRG-1:    Context Regime Gate (Doc 2 Amendment -- Context Regime Gate v1).
#            Profile A: New Hard HALT gate after Phase 2, before Pre-Check. Reads df_ctx
#            SMA_50/SMA_200 on last completed daily bar. HALT if Golden Cross absent
#            (SMA 50 < SMA 200) or price below SMA 200. Two new metrics:
#            Context_Golden_Cross (bool), Context_Price_vs_SMA200 (float).
#            Profile B: ma_stack_full extended to require SMA_50 > SMA_200 (Golden Cross).
#            Death Cross stocks can no longer reach TRENDING state. RESOLVING unaffected.
#            NaN guard: SMA_200 NaN → condition False → blocks TRENDING (Ambiguity Clause).
#            Profile C: Exempt (counter-cyclical thesis). No changes.
# ENG-005:   Context_SMA200 display bug (Data Normalisation). df_ctx daily bars are
#            in pence (GBx) for LSE equities, same as df hourly bars -- no internal
#            mismatch. Bug was display-only: Context_SMA200 written raw without
#            / price_scaler, causing a 100x scale discrepancy vs all other Operator-
#            facing price metrics. Fix: divide by price_scaler on output, matching
#            SMA_200, Price, Floor, Stop etc. Expectancy Gate & CRG-1 unaffected
#            (all cross-dataframe math is internally consistent in pence).
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio

# ==============================================================================
# ENG-001: ROUND NUMBER PROXIMITY HELPER  [Amendment ENG-001]
# Evaluates whether a price level falls within ±0.5% of the nearest round
# number. Two-tier increment: $5 for prices < $50, $10 for prices >= $50.
# Returns: 'NEAR_ROUND_ABOVE', 'NEAR_ROUND_BELOW', or 'CLEAR'.
# NON-GATE: informational only. Must not affect any verdict or gate threshold.
# ==============================================================================

def _check_round_number_proximity(price):
    """
    Returns 'NEAR_ROUND_ABOVE', 'NEAR_ROUND_BELOW', or 'CLEAR'.
    Increment: $5 for price < $50, $10 for price >= $50.
    Proximity threshold: ±0.5% of the round number.
    """
    if price is None or price <= 0:
        return "CLEAR"
    increment = 5.0 if price < 50.0 else 10.0
    import math
    nearest_below = math.floor(price / increment) * increment
    nearest_above = nearest_below + increment
    # Check proximity to nearest_below (round number is below current price)
    if nearest_below > 0 and abs(price - nearest_below) / nearest_below <= 0.005:
        return "NEAR_ROUND_ABOVE"   # level sits above the round number (round number is a floor below)
    # Check proximity to nearest_above (round number is above current price)
    if abs(price - nearest_above) / nearest_above <= 0.005:
        return "NEAR_ROUND_BELOW"   # level sits below the round number (round number is a ceiling above)
    return "CLEAR"


# ==============================================================================
# CLIMAX LOCKOUT HELPER  [MANDATE: DOC 2 SEC II]
# ==============================================================================

def check_climax_history(df):
    if df is None or len(df) < 4:
        return False, None
    required_cols = {"volume", "vol_sma_9", "close", "open"}
    if not required_cols.issubset(set(df.columns)):
        return False, None
    """
    Verifies the mandatory 3-bar block following a Volume Climax.
    Triggered: Volume > 2x SMA9 AND bar closes negative.
    Penalty:   Hard Block for 3 subsequent bars.
    """
    for i in range(1, 4):

        try:
            vol    = df['volume'].iloc[-i]
            sma9   = df['vol_sma_9'].iloc[-i]
            if pd.isna(sma9) or sma9 == 0:
                continue
            is_neg = df['close'].iloc[-i] < df['open'].iloc[-i]
            if vol > (2 * sma9) and is_neg:
                return True, i
        except (IndexError, KeyError):
            continue
    return False, 0


# ==============================================================================
# CHART BUILDERS  [MANDATE: DOC 4]
# Separated into pure functions. adx_col is passed explicitly to avoid
# hardcoding 'ADX_14' and to ensure robustness across pandas_ta versions.
# ==============================================================================

def _build_primary_chart(df, p_code, profile, clean_ticker, adx_col, dmp_col, dmn_col):
    """
    [MANDATE: DOC 4 SEC IV] Full-history Primary Execution Chart.
    Row 1: Candlesticks | SMA 50 | SMA 200 | EMA 8 | EMA 21 | VWAP (Profile A)
    Row 2: Volume | Vol SMA 9
    Row 3: ADX | +DI | -DI | ADX=20 threshold | ATR (secondary y)
    """
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        specs=[[{"secondary_y": False}],
               [{"secondary_y": False}],
               [{"secondary_y": True}]]
    )

    # Row 1: Price + MAs
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'],
        low=df['low'], close=df['close'], name="Price"
    ), row=1, col=1)

    ma_overlays = [
        ('SMA_50',  "SMA 50",  'red',    1.5),
        ('SMA_200', "SMA 200", 'white',  1.5),
        ('EMA_8',   "EMA 8",   'cyan',   1.5),
        ('EMA_21',  "EMA 21",  'yellow', 2.0),
    ]
    for col, name, color, width in ma_overlays:
        if col in df.columns and df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], name=name,
                line=dict(color=color, width=width)
            ), row=1, col=1)

    if p_code == "A":
        vwap_col = [c for c in df.columns if 'VWAP' in c]
        if vwap_col:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[vwap_col[0]], name="VWAP",
                line=dict(color='fuchsia', width=2)
            ), row=1, col=1)

    # Row 2: Volume
    vol_colors = [
        '#00FF00' if df['close'].iloc[i] >= df['open'].iloc[i] else '#FF0000'
        for i in range(len(df))
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df['volume'], name="Volume", marker_color=vol_colors
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['vol_sma_9'], name="Vol SMA 9",
        line=dict(color='orange')
    ), row=2, col=1)

    # Row 3: ADX + DI + ATR
    # [MANDATE: DOC 4 SEC IV] +DI and -DI mandatory for Directional Dominance check
    fig.add_trace(go.Scatter(
        x=df.index, y=df[adx_col], name="ADX 14",
        line=dict(color='purple', width=2)
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df[dmp_col], name="+DI",
        line=dict(color='lime', width=1, dash='dot')
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df[dmn_col], name="-DI",
        line=dict(color='tomato', width=1, dash='dot')
    ), row=3, col=1)
    # [MANDATE: DOC 2 SEC 4.2] ADX=20 MID-RANGE boundary
    fig.add_hline(
        y=20, line=dict(color='yellow', dash='dot', width=1),
        annotation_text="ADX=20 (MID-RANGE)",
        annotation_position="bottom right",
        row=3, col=1
    )
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ATRr_14'], name="ATR 14",
        line=dict(color='gray', width=1)
    ), row=3, col=1, secondary_y=True)

    fig.update_layout(
        template="plotly_dark", height=1100,
        title=f"TBS v8.6 Primary View: {clean_ticker} [{profile}]",
        xaxis_rangeslider_visible=False, showlegend=True
    )
    # Cap volume y-axis at the 99th percentile so a single earnings spike
    # cannot compress all other bars to invisible. The spike is simply clipped
    # at the top of the panel. Bar traces remain fully visible.
    # (Log scale breaks Plotly bar rendering -- percentile cap is correct fix.)
    vol_cap = float(df['volume'].quantile(0.99))
    fig.update_yaxes(range=[0, vol_cap * 1.05], row=2, col=1)
    return fig


def _build_context_chart(df_ctx, p_code, profile, clean_ticker):
    """
    [MANDATE: DOC 4 SEC II] Context Timeframe Chart (Triple-View Tier 2).
    Profile A -> Daily | Profile B -> Weekly | Profile C -> Monthly

    Defensive: each indicator is only plotted if its column exists and has
    at least one non-NaN value. A missing column never crashes the engine.

    CORRUPT DATA GUARD: Long-horizon IBKR requests (monthly/weekly 10-20Y)
    occasionally include erroneous unadjusted pre-split data in early bars.
    The full df_ctx is retained for MA calculations; only the last 60 bars
    are passed to the chart traces to suppress corrupt early data artifacts.
    """
    ctx_labels = {"A": "Daily", "B": "Weekly", "C": "Monthly"}
    ctx_label  = ctx_labels.get(p_code, "Context")

    # Clip to last 60 bars for plotting only -- preserves MA accuracy
    clip_bars  = min(60, len(df_ctx))
    df_plot    = df_ctx.iloc[-clip_bars:]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3]
    )
    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['open'], high=df_plot['high'],
        low=df_plot['low'], close=df_plot['close'], name="Price"
    ), row=1, col=1)

    overlay_specs = [
        ('SMA_50',  f"SMA 50 ({ctx_label})",  'red',    1.5),
        ('SMA_200', f"SMA 200 ({ctx_label})", 'white',  1.5),
        ('EMA_8',   f"EMA 8 ({ctx_label})",   'cyan',   1.5),
        ('EMA_21',  f"EMA 21 ({ctx_label})",  'yellow', 2.0),
    ]
    for col, name, color, width in overlay_specs:
        if col in df_plot.columns and df_plot[col].notna().any():
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot[col], name=name,
                line=dict(color=color, width=width)
            ), row=1, col=1)

    vol_colors = [
        '#00FF00' if df_plot['close'].iloc[i] >= df_plot['open'].iloc[i] else '#FF0000'
        for i in range(len(df_plot))
    ]
    fig.add_trace(go.Bar(
        x=df_plot.index, y=df_plot['volume'], name="Volume", marker_color=vol_colors
    ), row=2, col=1)
    # [PE-20 FIX] Volume SMA 9 overlay for visual climax detection at Context timeframe.
    # Without this, the Analyst cannot verify Volume > 2x SMA 9 on the higher timeframe
    # per Doc 4 §I HITL protocol and Doc 2 §II climax definition.
    if 'vol_sma_9' in df_plot.columns and df_plot['vol_sma_9'].notna().any():
        fig.add_trace(go.Scatter(
            x=df_plot.index, y=df_plot['vol_sma_9'], name="Vol SMA 9",
            line=dict(color='orange')
        ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", height=700,
        title=f"TBS v8.6 Context View ({ctx_label}): {clean_ticker} [{profile}]",
        xaxis_rangeslider_visible=False, showlegend=True
    )
    return fig


def _build_focus_chart(df, p_code, profile, clean_ticker, price_scaler,
                       adx_col, dmp_col, dmn_col):
    """
    [MANDATE: DOC 4 SEC VII] 10-Bar Focus View.
    - Strictly 10 COMPLETED bars (active bar excluded via iloc[-11:-1]).
    - Consolidation High and Low annotated.
    - All y-axes autoranged to the zoomed window.
    - Generated ONLY after a PASS verdict to keep /charts clean.
    - adx_col, dmp_col, dmn_col passed explicitly for robustness.
    """
    if len(df) < 12:
        raise ValueError("Insufficient bars for Focus Chart (requires >= 12).")
    # [PE-16 FIX] Profile A uses bar-close cadence: the evaluated bar is iloc[-2], so
    # the 10-bar Focus Window is iloc[-12:-2] (matching resistance_raw, est_hourly_low,
    # and Vol Trend Confirmation). For B/C, the evaluated bar is iloc[-1] and the
    # window is iloc[-11:-1]. The previous code used iloc[-11:-1] for ALL profiles,
    # creating a 1-bar offset for Profile A where the chart's Consolidation Range
    # included the evaluated bar and omitted the oldest bar in the computational window.
    focus_df  = df.iloc[-12:-2] if p_code == "A" else df.iloc[-11:-1]
    cons_high = focus_df['high'].max()
    cons_low  = focus_df['low'].min()

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        specs=[[{"secondary_y": False}],
               [{"secondary_y": False}],
               [{"secondary_y": True}]]
    )

    # Row 1: Price + MAs
    fig.add_trace(go.Candlestick(
        x=focus_df.index, open=focus_df['open'], high=focus_df['high'],
        low=focus_df['low'], close=focus_df['close'], name="Price"
    ), row=1, col=1)
    focus_ma_overlays = [
        ('SMA_50',  "SMA 50",  'red',    1.5),
        ('SMA_200', "SMA 200", 'white',  1.5),
        ('EMA_8',   "EMA 8",   'cyan',   1.5),
        ('EMA_21',  "EMA 21",  'yellow', 2.0),
    ]
    for col, name, color, width in focus_ma_overlays:
        if col in focus_df.columns and focus_df[col].notna().any():
            fig.add_trace(go.Scatter(
                x=focus_df.index, y=focus_df[col], name=name,
                line=dict(color=color, width=width)
            ), row=1, col=1)
    if p_code == "A":
        vwap_cols = [c for c in focus_df.columns if 'VWAP' in c]
        if vwap_cols:
            fig.add_trace(go.Scatter(
                x=focus_df.index, y=focus_df[vwap_cols[0]], name="VWAP",
                line=dict(color='fuchsia', width=2)
            ), row=1, col=1)

    # [MANDATE: DOC 2 SEC III / DOC 4 SEC VII] Consolidation Range
    # [PE-14 FIX] hline y-positions and annotations must use RAW values to match
    # the candlestick/MA data plotted on the same axis. The previous code divided
    # by price_scaler, placing the lines at 1/100th of the correct position on
    # GBP charts (pence data at ~181, hlines at ~1.81). price_scaler is a DISPLAY
    # conversion for the metrics payload and diagnostic strings; chart axes operate
    # in the same unit space as the underlying IBKR data (pence for GBP, dollars
    # for USD). Annotation text also stays in raw units for axis consistency.
    fig.add_hline(
        y=cons_high,
        line=dict(color='orange', dash='dash', width=1.5),
        annotation_text=f"Cons. High: {cons_high:.2f}",
        annotation_position="top right", row=1, col=1
    )
    fig.add_hline(
        y=cons_low,
        line=dict(color='orange', dash='dot', width=1.5),
        annotation_text=f"Cons. Low: {cons_low:.2f}",
        annotation_position="bottom right", row=1, col=1
    )

    # Row 2: Volume
    vol_colors = [
        '#00FF00' if focus_df['close'].iloc[i] >= focus_df['open'].iloc[i] else '#FF0000'
        for i in range(len(focus_df))
    ]
    fig.add_trace(go.Bar(
        x=focus_df.index, y=focus_df['volume'], name="Volume", marker_color=vol_colors
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=focus_df.index, y=focus_df['vol_sma_9'], name="Vol SMA 9",
        line=dict(color='orange')
    ), row=2, col=1)

    # Row 3: ADX + DI + ATR (use passed column names, no hardcoding)
    fig.add_trace(go.Scatter(
        x=focus_df.index, y=focus_df[adx_col], name="ADX 14",
        line=dict(color='purple', width=2)
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=focus_df.index, y=focus_df[dmp_col], name="+DI",
        line=dict(color='lime', width=1, dash='dot')
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=focus_df.index, y=focus_df[dmn_col], name="-DI",
        line=dict(color='tomato', width=1, dash='dot')
    ), row=3, col=1)
    fig.add_hline(
        y=20, line=dict(color='yellow', dash='dot', width=1),
        annotation_text="ADX=20", row=3, col=1
    )
    fig.add_trace(go.Scatter(
        x=focus_df.index, y=focus_df['ATRr_14'], name="ATR 14",
        line=dict(color='gray', width=1)
    ), row=3, col=1, secondary_y=True)

    # Autorange all y-axes to the 10-bar window for legibility
    fig.update_yaxes(autorange=True, row=1, col=1)
    fig.update_yaxes(autorange=True, row=2, col=1)
    fig.update_yaxes(autorange=True, row=3, col=1)
    fig.update_yaxes(autorange=True, row=3, col=1, secondary_y=True)

    fig.update_layout(
        template="plotly_dark", height=1100,
        title=f"TBS v8.6 Focus View (10-Bar Window): {clean_ticker} [{profile}]",
        xaxis_rangeslider_visible=False, showlegend=True
    )
    return fig


# ==============================================================================
# MAIN ENGINE
# ==============================================================================

def run_tbs_engine(ticker, profile="TREND", is_etf=False, mode="INFO",
                   exchange="SMART", currency="USD", convexity_class=None):

    # --- [MANDATE: CONCURRENCY INTEGRITY] ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # --- [CONVEXITY] Input validation (Redesign Proposal §4.1 / Execution Map §VI) ---
    # Valid classes: None (unclassified → C-1 behaviour), "C1", "C2", "C3".
    # None preserves full backward compatibility: all outputs identical to v8.6.
    _VALID_CONVEXITY = {None, "C1", "C2", "C3"}
    if convexity_class not in _VALID_CONVEXITY:
        return "ERROR", f"INVALID CONVEXITY CLASS: '{convexity_class}'. Valid: None, 'C1', 'C2', 'C3'.", {}
    _is_c3 = (convexity_class == "C3")

    unique_client_id = 25 + (os.getpid() % 100)
    port = 4002 if mode.upper() == "INFO" else 4001

    ib      = IB()

    # Suppress Error 162 (NYSENBBO routing) from console output.
    # ib_insync logs errors via its internal logger independently of errorEvent,
    # so the only reliable suppression is a logging filter on the wrapper logger.
    # Errors 2104/2106/2158 (connection confirmations) are left to ib_insync defaults.
    import logging
    class _SuppressError162(logging.Filter):
        def filter(self, record):
            return 'Error 162' not in record.getMessage()
    logging.getLogger('ib_insync.wrapper').addFilter(_SuppressError162())

    metrics = {}  # [MANDATE: DOC 8 SEC 39] SSoT Handshake initialisation

    # --- [MANDATE: DOC 8 SEC 23] DYNAMIC ROUTING ---
    clean_ticker = ticker.upper()
    p_exchange   = ""
    routing_map  = {
        '.L':  {'exchange': 'SMART', 'currency': 'GBP', 'primary': 'LSE'},
        '.TO': {'exchange': 'SMART', 'currency': 'CAD', 'primary': 'TSE'},
        '.DE': {'exchange': 'IBIS',  'currency': 'EUR', 'primary': 'IBIS'},
        '.AS': {'exchange': 'AEB',   'currency': 'EUR', 'primary': 'AEB'},
        '.PA': {'exchange': 'SBF',   'currency': 'EUR', 'primary': 'SBF'},
    }
    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exchange'], route['currency'], route['primary']
            break

    if clean_ticker == "VWRP" and currency == "USD":
        exchange, currency, p_exchange = "SMART", "GBP", "LSE"

    try:
        script_dir   = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        chart_dir    = os.path.join(project_root, "charts")
        if not os.path.exists(chart_dir):
            os.makedirs(chart_dir)

        # [MANDATE: CHART INTEGRITY] Purge all existing charts for this ticker
        # before the run begins. Guarantees no stale chart from a prior run
        # (e.g. a Focus chart from a previous PASS) survives a re-scan.
        for suffix in ("_primary.png", "_context.png", "_focus.png"):
            try:
                os.remove(os.path.join(chart_dir, f"{clean_ticker}{suffix}"))
            except FileNotFoundError:
                pass


        ib.connect('127.0.0.1', port, clientId=unique_client_id)

        ib.reqMarketDataType(1)

        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)

        # --- [MANDATE: DOC 8 SEC 467] INDEPENDENT ASSET IDENTIFICATION ---
        _is_lse_etf = False   # [PE-3] Flag for LSE ETFs that trade in pounds, not pence
        details = ib.reqContractDetails(contract)
        if details:
            meta = details[0].longName.upper()
            etf_keywords = [
                'ETF', 'FUND', 'VANGUARD', 'VANG', 'ISHARES', 'UCITS',
                'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES'
            ]
            if any(key in meta for key in etf_keywords):
                is_etf = True

            # Use the fully-qualified contract returned by IBKR (correct conid + exchange).
            # This prevents SMART routing to quote-only feeds (e.g. NYSENBBO) that carry
            # no historical data -- common for foreign-domiciled NYSE listings such as LIN.
            # ib_insync: primaryExchange lives on Contract; primaryExch on ContractDetails.
            qualified = details[0].contract
            primary_exch = getattr(qualified, 'primaryExchange', '') or getattr(details[0], 'primaryExch', '')
            # [PE-3 FIX] IBKR uses dedicated exchange codes for ETFs (e.g. LSEETF).
            # This catches ETFs whose abbreviated longName misses keyword detection
            # (e.g. "VANG S&P500 USDA" lacks both 'ETF' and 'VANGUARD').
            if 'ETF' in primary_exch.upper():
                is_etf = True
                _is_lse_etf = True   # LSE ETFs trade in pounds, not pence
            if primary_exch == 'NYSENBBO':
                qualified.primaryExchange = 'NYSE'
            contract = qualified

        # --- PROFILE & TIMEFRAME MAPPING ---
        p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
        p_code    = p_mapping.get(profile.upper())
        if p_code is None:
            return "ERROR", (f"INVALID PROFILE: '{profile}' not recognised. "
                             f"Valid: SWING (A), TREND (B), WEALTH (C)."), {}
        tf_map    = {"A": ("1 hour", "3 M"), "B": ("1 day", "2 Y"), "C": ("1 week", "10 Y")}
        res, dur  = tf_map[p_code]

        bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True)

        # --- NYSENBBO RETRY GUARD ---
        # Some foreign-domiciled US listings (e.g. LIN/Linde) are routed by IBKR
        # to the NYSENBBO quote-only feed regardless of the primaryExchange returned
        # by reqContractDetails (which may itself be wrong, e.g. NASDAQ for a NYSE stock).
        # If the first attempt returns no data, force exchange=NYSE and retry once.
        # [PE-1 FIX] Only retry for USD-denominated contracts. NYSE does not trade
        # foreign-currency securities; retrying GBP/EUR/CAD tickers wastes an API call
        # and generates confusing "No security definition" errors.
        nyse_retry_used = False
        if not bars and currency == "USD":
            contract.exchange        = 'NYSE'
            contract.primaryExchange = 'NYSE'
            bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True)
            nyse_retry_used = bool(bars)

        if not bars:
            return "ERROR", f"No data retrieved for {clean_ticker}", {}

        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        # --- NYSE RETRY VOLUME PATCH ---
        # When the NYSE retry was used, the price/OHLC data is correct but volume
        # reflects only NYSE venue activity (thin). SMART routing aggregates volume
        # across all venues and gives the accurate consolidated figure needed for ADV.
        # Fetch a short SMART volume-only series and overwrite df['volume'] so that
        # the ADV gate uses consolidated volume while OHLC data remains from NYSE.
        if nyse_retry_used:
            smart_contract = Stock(clean_ticker, 'SMART', currency)
            vol_dur = '3 M' if 'day' in res else ('6 M' if 'week' in res else '2 Y')
            try:
                vol_bars = ib.reqHistoricalData(smart_contract, '', vol_dur, res, 'TRADES', True)
                if vol_bars:
                    df_vol = util.df(vol_bars)
                    df_vol.set_index('date', inplace=True)
                    df_vol.index = pd.to_datetime(df_vol.index)
                    df_vol.sort_index(inplace=True)
                    # Align on index -- only overwrite where both have data
                    common_idx = df.index.intersection(df_vol.index)
                    if len(common_idx) > 10:
                        df.loc[common_idx, 'volume'] = df_vol.loc[common_idx, 'volume']
            except Exception:
                pass   # If SMART volume fetch fails, retain NYSE volume silently

        # --- DATA SUFFICIENCY GUARD (deterministic HALT) ---
        # Minimum bars needed to support:
        # - 10-bar Focus Window (10 completed bars + current bar)
        # - ADX slope check (t, t-1, t-2)
        # - SMA20 volume for ADV gate
        # --- DATA SUFFICIENCY GUARD (deterministic HALT) ---
        # Minimum bars required is profile-dependent:
        #   Profile A (hourly)  : 30  bars  -- SMA_200 not used as floor; ADX/ATR need ~20
        #   Profile B (daily)   : 220 bars  -- SMA_200 daily floor needs 200 bars to initialise
        #   Profile C (weekly)  : 220 bars  -- SMA_200 weekly floor needs 200 bars to initialise
        # Without this guard, pandas_ta silently skips the SMA_200 column when
        # history is insufficient, causing a downstream KeyError crash.
        min_bars_required = 30 if p_code == "A" else 220
        if len(df) < min_bars_required:
            return (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). Insufficient historical data: {len(df)} bars retrieved "
                f"(requires >= {min_bars_required} for Profile {p_code}). "
                f"Ticker may be too new or have limited exchange history for SMA_200 calculation.",
                metrics
            )

        # --- TIMEFRAME NORMALIZATION ---
        bars_per_day = (
            8.0 if currency == "GBP" else
            8.5 if currency == "EUR" else
            6.5
        ) if "hour" in res else (
            1.0 / 5.0  if "week"  in res else   # weekly bar  = 5 trading days -> daily = bar / 5
            1.0 / 21.0 if "month" in res else    # monthly bar = ~21 trading days -> daily = bar / 21
            1.0                                   # daily bar   = 1 day (no conversion needed)
        )
        sma_20_length = int(20 * bars_per_day) if "hour" in res else (
            20  if "day"   in res else   # 20 daily bars  = 4 weeks
            20  if "week"  in res else   # 20 weekly bars = ~5 months (best proxy for Profile C weekly)
            12  if "month" in res else   # 12 monthly bars = 1 year (Profile C monthly context)
            20
        )

        # --- INDICATOR STACK ---
        df.ta.ema(length=8,  append=True)
        df.ta.ema(length=21, append=True)
        df.ta.sma(length=50,  append=True)
        df.ta.sma(length=200, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.sma(close=df['volume'], length=9,             append=True, col_names=('vol_sma_9',))
        df.ta.sma(close=df['volume'], length=sma_20_length, append=True, col_names=('vol_sma_20',))

        # --- MA COLUMN EXISTENCE GUARD ---
        # pandas_ta silently skips writing a column when all computed values are NaN
        # (e.g. SMA_200 on a ticker with < 200 bars). Catch this here with a clean
        # HALT rather than a downstream KeyError crash.
        required_ma_cols = {
            "A": ["EMA_8", "EMA_21", "SMA_50"],
            "B": ["EMA_8", "EMA_21", "SMA_50", "SMA_200"],
            "C": ["EMA_8", "EMA_21", "SMA_50", "SMA_200"],
        }
        for col in required_ma_cols.get(p_code, []):
            if col not in df.columns or df[col].isna().all():
                return (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {col} is entirely NaN. "
                    f"Insufficient price history for this indicator on {clean_ticker}.",
                    metrics
                )

        # [PE-18 / PE-24 FIX] Existence guard for ATR and Volume SMA columns.
        # pandas_ta silently skips columns when computation fails. Without this guard,
        # downstream access (atr_raw at line ~760, vol_sma_9 at line ~844, adv_20 at
        # line ~826) crashes with KeyError rather than a clean HALT diagnostic.
        for ind_col in ['ATRr_14', 'vol_sma_9', 'vol_sma_20']:
            if ind_col not in df.columns or df[ind_col].isna().all():
                return (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {ind_col} is entirely NaN or missing. "
                    f"pandas_ta may have failed for {clean_ticker}.",
                    metrics
                )

        # --- COLUMN IDENTIFICATION (dynamic -- never hardcode column names) ---
        adx_candidates = [c for c in df.columns if c.startswith('ADX') and 'DM' not in c]
        dmp_candidates = [c for c in df.columns if 'DMP' in c]
        dmn_candidates = [c for c in df.columns if 'DMN' in c]

        if not adx_candidates:
            return "HALT", "REJECT (reason: DATA INTEGRITY). ADX column not found -- pandas_ta.adx() failed or insufficient data.", metrics
        if not dmp_candidates or not dmn_candidates:
            return "HALT", "REJECT (reason: DATA INTEGRITY). Directional Movement columns (DI+/DI-) not found.", metrics

        adx_col = adx_candidates[0]
        dmp_col = dmp_candidates[0]
        dmn_col = dmn_candidates[0]

        # [PE-9 FIX] Profile A bar-close cadence: ADX, DI, and MA Squeeze must
        # reference the last COMPLETED bar, not the live opening-stub bar.
        # Without this shift, partial intrabar data can flicker Engine State
        # (ADX 19.8 completed -> 20.1 live = phantom RESOLVING), bypass or
        # false-trigger the DI gate, and mis-fire the squeeze condition.
        # p_code is already resolved (line ~418) so it is safe to branch here.
        _iq = -2 if p_code == "A" else -1   # indicator query index

        adx_t   = df[adx_col].iloc[_iq]
        adx_t1  = df[adx_col].iloc[_iq - 1]
        adx_t2  = df[adx_col].iloc[_iq - 2]
        di_plus  = df[dmp_col].iloc[_iq]
        di_minus = df[dmn_col].iloc[_iq]

        # [PE-19 FIX] NaN guard on ADX/DI values before any comparison chain.
        # In NumPy, NaN < 20 → False AND NaN > 20 → False. Without this guard,
        # a NaN ADX silently bypasses the MID-RANGE gate (adx_t < 20 → False)
        # and falls through to AMBIGUOUS with a misleading diagnostic. The asset
        # should receive an explicit HALT with an actionable message.
        if any(pd.isna(v) for v in [adx_t, adx_t1, adx_t2, di_plus, di_minus]):
            return (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). ADX/DI indicator values contain NaN at evaluated bar. "
                f"Insufficient data for trend classification on {clean_ticker}.",
                metrics
            )

        # ======================================================================
        # ADX SLOPE ACCELERATION (Second Derivative)  [MANDATE: DOC 2 SEC 4.2.2]
        #
        # Distinguishes between a trend gaining momentum, at cruise speed,
        # or losing steam -- even while ADX remains above 25.
        #   accel > 0  : ACCELERATING -- momentum building, pullback further away
        #   accel ≈ 0  : CRUISING     -- steady state, standard pullback timing
        #   accel < 0  : DECELERATING -- momentum fading, pullback approaching
        #
        # Threshold: |accel| <= 0.3 is treated as CRUISING (noise floor).
        # Stateless: pure computation on existing ADX values, no persistent state.
        # ======================================================================
        adx_slope_t  = adx_t  - adx_t1
        adx_slope_t1 = adx_t1 - adx_t2
        adx_accel    = round(adx_slope_t - adx_slope_t1, 2)
        adx_accel_state = (
            "ACCELERATING" if adx_accel > 0.3 else
            "DECELERATING" if adx_accel < -0.3 else
            "CRUISING"
        )

        # --- [MANDATE: DOC 2 SEC 4.2] MA SQUEEZE ---
        df['MA_Dist'] = abs(df['EMA_8'] - df['EMA_21'])
        df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])
        ma_squeeze    = bool(
            df['Squeeze'].iloc[_iq] and df['Squeeze'].iloc[_iq - 1] and df['Squeeze'].iloc[_iq - 2]
        )

        # Use last completed bar for Profile A (1H) to enforce BAR CLOSE cadence.
        last = df.iloc[-2] if p_code == "A" else df.iloc[-1]

        # ======================================================================
        # ENGINE STATE CLASSIFICATION  [MANDATE: DOC 2 SEC 4.2]
        #
        # MID-RANGE  : ADX < 20 OR MA squeeze        -> HARD WAIT
        # RESOLVING  : ADX > 20 + 3-bar slope        -> Convexity/Breakout protocol
        # TRENDING   : ADX > 25 + full MA stack       -> Standard/Pullback protocol
        #
        # TRENDING takes precedence when both conditions are met.
        # ETF Logic Lock overrides both to baseline-floor protocols.
        # ======================================================================

        # RESOLVING: ADX > 20, 3-bar positive slope, no squeeze
        is_resolving = (
                (adx_t > 20) and
                (adx_t > adx_t1 > adx_t2) and
                not ma_squeeze
        )

        # TRENDING: ADX > 25 AND full 4-level MA stack (Price > EMA8 > EMA21 > SMA50)
        # State Persistence Rule  [MANDATE: DOC 2 SEC 4.2]
        # Initial confirmation requires ADX > 25 + full MA stack.
        # Persistence during pullback: ADX may soften to 20-25 by mathematical
        # construction (Wilder) while the MA stack remains intact. As long as
        # ADX > 20 (directional regime confirmed) AND MA stack is fully stacked,
        # TRENDING state is preserved. If MA stack breaks, state revokes immediately
        # regardless of ADX level.
        ma_stack_full = (
                last['close']  > last['EMA_8']  and
                last['EMA_8']  > last['EMA_21'] and
                last['EMA_21'] > last['SMA_50'] and
                # [CRG-1] Golden Cross: Profile B TRENDING requires SMA 50 > SMA 200.
                # Profile A: handled by Context Regime Gate. Profile C: exempt (counter-cyclical).
                # NaN guard: NaN SMA_200 evaluates False, blocking TRENDING (Ambiguity Clause §XI).
                (p_code != "B" or (not pd.isna(last['SMA_200']) and last['SMA_50'] > last['SMA_200']))
        )
        is_trending = ma_stack_full and (adx_t > 20) and not ma_squeeze

        # EMA stacked: EMA8 > EMA21 -- used solely for Profile A DI exemption
        ema_stacked = last['EMA_8'] > last['EMA_21']

        # ETF Logic Lock  [Doc 6 §3.4.1 / Doc 2 §4.2.1]
        # Suppresses EMA 8 floor re-assignment by zeroing is_trending / is_resolving.
        # These zeroed flags correctly prevent Convexity Protocol activation (ANCHOR
        # stays baseline MA, no EMA 8 exit signal, no EMA 8 proximity anchor).
        # Entry eligibility is preserved separately via _etf_entry_* snapshots
        # so Phase 4 can still route ETFs through Pullback / Breakout / Reclaim
        # protocols using their baseline floors.  [PE-BUG-1 FIX]
        if is_etf:
            _etf_entry_trending  = is_trending    # snapshot before Lock
            _etf_entry_resolving = is_resolving   # snapshot before Lock
            is_resolving = False                  # Lock: floor policy only
            is_trending  = False                  # Lock: floor policy only
        else:
            _etf_entry_trending  = False
            _etf_entry_resolving = False

        # [BUG #40 FIX -- REFINED] Demote RESOLVING when ADX slope is positive but
        # the structural direction is bearish. ADX measures trend STRENGTH, not
        # direction -- a rising ADX with -DI > +DI means the DOWNTREND is
        # strengthening, not that a bullish regime is forming.
        #
        # Original fix used a 15-point DI-spread threshold which proved too wide:
        #   ISRG TREND:  spread 14.88 -- missed (EMA inverted, price $40 below SMA_50)
        #   ISRG WEALTH: spread 10.46 -- missed (EMA inverted, clearly bearish weekly)
        #
        # Revised criteria -- ALL must be true:
        #   1. is_resolving is True (ADX > 20, 3-bar positive slope)
        #   2. EMA stack is inverted (EMA_8 < EMA_21) -- short-term structure broken.
        #      This is the primary structural signal. A bullish RESOLVING setup
        #      requires the fast EMA above the slow EMA to support the breakout thesis.
        #   3. -DI > +DI -- directional flow confirms downside, not upside.
        #      Combined with EMA inversion this is unambiguous bearish context.
        #   4. MA stack is not full -- no structural bull confirmation exists.
        #
        # The DI spread magnitude is dropped as a criterion. Any -DI dominance on
        # an inverted EMA stack is sufficient -- the threshold was arbitrary and
        # generated false negatives on legitimate demotion candidates.
        _resolving_is_bearish = (
                is_resolving and
                not ema_stacked and       # EMA_8 < EMA_21: short-term structure broken
                (di_minus > di_plus) and  # -DI dominant: directional flow is bearish
                not ma_stack_full         # no bullish MA confirmation
        )
        # [PE-CAL-1 FIX §6.6] Profile C counter-cyclical exemption. WEALTH entries
        # at the SMA 200 are inherently counter-cyclical: the asset has declined to its
        # long-term floor, so -DI dominance and EMA inversion are expected by construction.
        # Demotion is suppressed when price is within 5% of SMA 200 AND ADX slope is
        # positive (directional energy building, even if currently bearish).
        _c_near_floor = False
        if p_code == "C" and 'SMA_200' in df.columns and not pd.isna(last['SMA_200']) and last['SMA_200'] > 0:
            _c_floor_dist_pct = abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100
            _c_near_floor = _c_floor_dist_pct <= 5.0 and (adx_t > adx_t1)  # within 5% + positive ADX slope
        if _resolving_is_bearish and not _c_near_floor:
            is_resolving = False

        # [PE-BUG-1 FIX] Apply identical bearish demotion to ETF entry snapshot.
        # Without this, an ETF with inverted EMAs and -DI dominance would still
        # reach Phase 4 RESOLVING branch via the _etf_entry_resolving flag.
        if _etf_entry_resolving and not ema_stacked and (di_minus > di_plus) and not ma_stack_full:
            _etf_entry_resolving = False

        # Composite entry-eligibility flags  [PE-BUG-1 FIX]
        # Used at Phase 4 decision chain + Gate 6 DI exemption.
        # For non-ETF: _etf_entry_* are False, so these equal is_trending/is_resolving.
        # For ETF: is_trending/is_resolving are False (Lock), so these equal _etf_entry_*.
        _entry_trending  = is_trending  or _etf_entry_trending
        _entry_resolving = is_resolving or _etf_entry_resolving

        # ======================================================================
        # STRUCTURAL FLOOR MAPPING  [MANDATE: DOC 2 SEC 4.1]
        # Profile A = VWAP
        # Profile B = Daily 50-SMA (baseline) OR EMA 8 (if RESOLVING, non-ETF)
        # Profile C = Weekly 200-SMA
        # ETF = immutable baseline MA, never EMA 8
        # ======================================================================

        # [BUG #35 FIX] ETF Profile A guard removed.
        # The ETF exemption blocks EMA 8 floor re-assignment during the Convexity
        # Protocol (RESOLVING state) on Profile B/C. For Profile A, the floor is
        # immutably VWAP regardless of ETF status or engine state -- the ETF flag
        # has zero operative effect here. The previous guard returned HALT + empty
        # metrics, refusing all valid ETF SWING scans. ETF Profile A now falls
        # through to the standard VWAP block below, identically to non-ETF Profile A.
        if is_etf:
            if p_code == "B":
                df['ANCHOR'] = df['SMA_50']
            elif p_code == "C":
                df['ANCHOR'] = df['SMA_200']
            elif p_code == "A":
                pass   # ETF flag inert on Profile A -- fall through to VWAP block below
            else:
                return "HALT", f"REJECT (reason: DATA INTEGRITY). Unknown profile code for ETF routing: {p_code}", metrics

        if p_code == "A":
            df.ta.vwap(append=True)
            vwap_cols = [c for c in df.columns if 'VWAP' in c]
            if not vwap_cols:
                return "HALT", "REJECT (reason: DATA INTEGRITY). VWAP column not found -- pandas_ta.vwap() failed or insufficient data.", metrics
            vwap_col     = vwap_cols[0]
            df['ANCHOR'] = df[vwap_col]
        elif p_code == "B":
            # EMA_8 floor re-assignment applies only to RESOLVING state.
            # When TRENDING, the baseline SMA_50 floor is maintained -- TRENDING
            # takes priority over RESOLVING when both flags are simultaneously true.
            # [BUG #41 FIX] Additional guard: ema_stacked (EMA_8 > EMA_21) required.
            # The Convexity Protocol assigns EMA_8 as dynamic support for a breakout
            # setup -- this is only structurally valid when EMA_8 is above EMA_21
            # (fast MA leading slow MA upward). When EMA_8 < EMA_21, the EMA stack
            # is bearishly inverted and EMA_8 is overhead resistance, not support.
            # Assigning an inverted EMA_8 as the floor understates the true breach
            # depth and misrepresents the structural context. In this condition the
            # Convexity re-assignment is blocked and SMA_50 baseline is retained.
            _convexity_eligible = is_resolving and not is_trending and ema_stacked
            df['ANCHOR'] = df['EMA_8'] if _convexity_eligible else df['SMA_50']
        elif p_code == "C":
            df['ANCHOR'] = df['SMA_200']

        # Re-read last row after ANCHOR column is computed
        last = df.iloc[-2] if p_code == "A" else df.iloc[-1]

        # --- PRE-COMPUTE RESISTANCE  [MANDATE: PHASE ORDER INTEGRITY] ---
        # Must be defined before Phase 1.5 Expectancy Gate to prevent NameError
        # in the cons_high fallback branch (price above daily 10-bar range).
        # Phase 4 reads this same variable -- no duplication, just early definition.
        resistance_raw = (
            float(df['high'].iloc[-12:-2].max()) if p_code == "A"
            else float(df['high'].iloc[-11:-1].max())
        )

        # --- SCALING & HARD STOP  [MANDATE: DOC 8 SEC 465] ---
        # [PE-3 FIX] LSE ETFs (primaryExchange=LSEETF) trade in pounds, not pence.
        # The GBP รท100 scaler must NOT apply -- it deflates all metrics 100x,
        # causing false liquidity failures and nonsensical Price/Floor/Stop/ATR values.
        price_scaler         = 1.0 if _is_lse_etf else (100.0 if currency == "GBP" else 1.0)
        actual_price         = last['close'] / price_scaler
        atr_raw              = float(last['ATRr_14'])
        structural_floor_raw = last['ANCHOR']

        # [BUG #43 FIX] Profile A hard_stop must always anchor to structural_floor_raw
        # (VWAP), not min(last['low'], VWAP). The previous min() logic intended to
        # account for intra-bar wicks below VWAP, but it produces a stop that drifts
        # below the structural floor whenever the bar's low dips under VWAP -- including
        # in violated states where price close is already below VWAP. In that case,
        # min(last['low'], VWAP) = last['low'], anchoring the stop to current price
        # rather than the floor. The stop then understates risk by exactly the violation
        # depth, misrepresenting the structural reference to the Operator.
        # Fix: unconditionally anchor to structural_floor_raw for all profiles.
        # VWAP is the Structural Floor for Profile A regardless of bar low.
        hard_stop_raw = structural_floor_raw - (1.5 * atr_raw)

        # --- SSG-001: STRUCTURAL STOP AUDIT  [Spec Section 2.2] ---
        # If the hard stop sits above the Established Hourly Low, a normal
        # consolidation test of the hourly low would trigger the stop before
        # reaching actual support. Push the stop below the hourly low with
        # a 0.25 ATR buffer for structural clearance.
        # SSG-001 fires BEFORE CEG-001 so the Capital Expectancy Gate evaluates
        # against the corrected stop (wider stop = more capital at risk).
        _ssg_adjusted = False
        _ssg_original_raw = None
        _ssg_reason = None
        if p_code == "A":
            _ssg_hourly_low = float(df['low'].iloc[-12:-2].min())
            if hard_stop_raw > _ssg_hourly_low:
                _ssg_original_raw = hard_stop_raw
                hard_stop_raw = _ssg_hourly_low - (0.25 * atr_raw)
                _ssg_adjusted = True
                _ssg_reason = (
                    f"Hard stop ({round(_ssg_original_raw / price_scaler, 2)}) above "
                    f"Established Hourly Low ({round(_ssg_hourly_low / price_scaler, 2)}). "
                    f"Pushed to {round(hard_stop_raw / price_scaler, 2)} "
                    f"(Hourly Low - 0.25 ATR)."
                )

        # --- PROXIMITY ANCHOR  [MANDATE: DOC 2 SEC VIII] ---
        # Decoupled from Structural Floor -- used for Extension Gate only.
        # Profile A anchor MUST be VWAP per Doc 2 Sec VIII: "Profile A: 1.5 ATR from VWAP."
        # Profile B RESOLVING: EMA 8 | Profile B TRENDING: EMA 21
        # Profile C: EMA 21 (Weekly) | ETF: baseline MA (SMA 50 / SMA 200)
        # [BUG #37 FIX] ETF Profile A must use VWAP as proximity anchor -- not SMA_200.
        # The previous ETF block assigned SMA_200 for any non-B profile (including A),
        # producing a spurious ATR_Dist of ~8.6 and an inverted ATR_Dist_Note.
        # ETF flag is inert for Profile A (VWAP is immutable regardless of ETF status).
        if is_etf:
            if p_code == "A":
                prox_anchor = last[vwap_col]   # ETF Profile A: VWAP anchor (same as non-ETF)
            elif p_code == "B":
                prox_anchor = last['SMA_50']
            else:
                prox_anchor = last['SMA_200']  # Profile C ETF
        elif p_code == "A":
            prox_anchor = last[vwap_col]   # [MANDATE: DOC 2 SEC VIII] VWAP is the Profile A anchor
        elif p_code == "C":
            # [PE-CAL-1 FIX §6.4] Profile C anchor realigned to SMA 200 (Structural Floor).
            # Previously EMA 21, which created dual-anchor impossibility: extension measured
            # distance from EMA 21 while floor proximity measured distance from SMA 200.
            # Both gates now measure the same structural relationship: proximity to the
            # long-term floor. Concentric circles around a single reference point.
            prox_anchor = last['SMA_200']
        else:
            # Profile B: TRENDING -> EMA_21 anchor | RESOLVING (only) -> EMA_8 anchor
            # Guard: if both flags are true, TRENDING wins and EMA_21 is used.
            prox_anchor = last['EMA_8'] if (is_resolving and not is_trending) else last['EMA_21']

        atr_dist = (last['close'] - prox_anchor) / atr_raw

        # --- EXTENSION LIMIT  [MANDATE: DOC 2 SEC VIII] ---
        # State and Profile dependent. Computed here (before Morphology) so
        # both Modifier D and Gate 5 reference the same value -- single source of truth.
        #
        #   Profile A (SWING)      : 1.5 ATR  -- hourly timeframe compression
        #   Profile B RESOLVING    : 0.5 ATR  -- EMA 8 anchor, tight compression required
        #     [PE-CAL-1] Breakout bar: 1.5 ATR ceiling (exemption applied at Gate 5)
        #   Profile B TRENDING     : 1.0 ATR  -- EMA 21 anchor, accommodates MA lag in live trend
        #   Profile C (WEALTH)     : 1.0 ATR  -- SMA 200 anchor [PE-CAL-1 §6.4 realignment]
        #   ETF (Profiles B/C)    : 0.5 ATR  -- conservative baseline, no state differentiation
        #   ETF (Profile A)       : 1.5 ATR  -- identical to non-ETF Profile A (§VIII.1)
        if p_code == "A":
            ext_limit = 1.5
        elif p_code == "C":
            ext_limit = 0.5 if is_etf else 1.0   # [PE-CAL-1 §6.4] SMA 200 anchor, widened from 0.5
        elif is_etf:
            ext_limit = 0.5
        elif is_trending:
            ext_limit = 1.0   # Profile B TRENDING -- wider tolerance for EMA 21 lag
        else:
            ext_limit = 0.5   # Profile B RESOLVING or AMBIGUOUS -- tight

        # --- ADV  [MANDATE: DOC 2 SEC II] ---
        adv_20 = float((df['vol_sma_20'].iloc[-1] * actual_price) * bars_per_day)

        # ======================================================================
        # MORPHOLOGY -- MODIFIERS A, B, C, D  [MANDATE: DOC 2 SEC VII]
        # Visual estimation strictly prohibited; all conditions mathematical.
        # ======================================================================

        total_range = last['high'] - last['low']
        real_body   = abs(last['close'] - last['open'])
        # Profile A last = df.iloc[-2], so "previous bar" is one further back.
        prev_high   = df['high'].iloc[-3] if p_code == "A" else df['high'].iloc[-2]
        prev_low    = df['low'].iloc[-3]  if p_code == "A" else df['low'].iloc[-2]

        # [MANDATE: BAR-CLOSE CADENCE] For Profile A, vol_sma_9 must reference the
        # last COMPLETED bar (iloc[-2]). Using iloc[-1] includes the live opening-stub
        # bar -- its partial volume deflates the SMA, making Modifiers B and D
        # marginally easier to trigger than the mandate intends.
        # The climax filter applies the same discipline (passes df.iloc[:-1]).
        _vol_sma9_ref = df['vol_sma_9'].iloc[-2] if p_code == "A" else df['vol_sma_9'].iloc[-1]

        # Modifier A: Structural Rejection Bar
        mod_a = (
                (total_range > (0.5 * atr_raw)) and
                (last['low']   < last['ANCHOR']) and
                (last['close'] > last['ANCHOR']) and
                ((min(last['open'], last['close']) - last['low']) > (0.6 * total_range))
        )

        # Modifier B: Momentum Ignition Bar
        mod_b = (
                (last['close'] > prev_high) and
                (real_body > (0.7 * total_range)) and
                (last['volume'] > _vol_sma9_ref)
        )

        # Modifier C: Compression Bar
        mod_c = (
                (last['high'] < prev_high) and
                (last['low']  > prev_low) and
                (abs(last['close'] - last['ANCHOR']) <= (0.5 * atr_raw))
        )

        # Modifier D: Institutional Churn (Early Warning Exit)
        # EXTENDED condition uses the same state-dependent ext_limit as Gate 5
        # [MANDATE: DOC 2 SEC VII / SEC VIII] -- single source of truth for EXTENDED definition.
        mod_d_vol   = last['volume'] > (1.5 * _vol_sma9_ref)
        mod_d_body  = (real_body < (0.25 * total_range)) if total_range > 0 else False
        mod_d_state = (
            "ACTIVE (Inst. Churn)" if (atr_dist > ext_limit) and mod_d_vol and mod_d_body
            else "CLEAR (No Churn)"
        )
        # [CONVEXITY] Modifier D annotation for C-3 (Redesign Proposal §6.2 / Execution Map §VI)
        # C-3 positions have open-ended reward; institutional churn at extended levels is
        # expected volatility, not a structural exit signal. The flag is surfaced for operator
        # awareness but does not mandate action.
        if _is_c3 and mod_d_state.startswith("ACTIVE"):
            mod_d_state = "INFORMATIONAL (Inst. Churn -- C-3: no action mandated)"

        # Conviction state for Convexity sizing multiplier
        conviction_state = (
            "LOW (Range < 1.2 ATR)"  if total_range < (1.2 * atr_raw)
            else "HIGH (Range > 1.2 ATR)"
        )

        active_mods = []
        if mod_a: active_mods.append("A (Rejection)")
        if mod_b: active_mods.append("B (Ignition)")
        if mod_c: active_mods.append("C (Compression)")

        # ======================================================================
        # VOLUME TREND CONFIRMATION RATIO  [MANDATE: DOC 2 SEC 4.2.2]
        #
        # Measures institutional participation alignment over the 10-bar Focus
        # Window. Counts above-average-volume bars on up-closes vs down-closes.
        #   > 0.7  : STRONG INSTITUTIONAL -- accumulation dominates
        #   0.4-0.7: MIXED               -- no clear institutional commitment
        #   < 0.4  : DISTRIBUTION WARNING -- selling despite rising price
        #
        # Profile A uses iloc[-12:-2] (bar-close cadence); B/C use iloc[-11:-1].
        # Stateless: single pass over existing columns, no persistent state.
        # ======================================================================
        _vw_slice = df.iloc[-12:-2] if p_code == "A" else df.iloc[-11:-1]
        _up_vol   = int((((_vw_slice['close'] > _vw_slice['open']) &
                          (_vw_slice['volume'] > _vw_slice['vol_sma_9']))).sum())
        _dn_vol   = int((((_vw_slice['close'] < _vw_slice['open']) &
                          (_vw_slice['volume'] > _vw_slice['vol_sma_9']))).sum())
        _vol_total = _up_vol + _dn_vol
        vol_confirm_ratio = round(_up_vol / max(_vol_total, 1), 2)
        vol_confirm_state = (
            "STRONG INSTITUTIONAL" if vol_confirm_ratio > 0.7 else
            "DISTRIBUTION WARNING" if vol_confirm_ratio < 0.4 else
            "MIXED"
        )

        # ======================================================================
        # EXECUTION WINDOW BINDING  [MANDATE: DOC 2 SEC III]
        #
        # Is_Breakout : close strictly above the preceding 10-bar high.
        # Is_Pullback : PURELY POSITIONAL -- Price in [Floor, Floor + 0.5 ATR].
        #   No morphological criteria. Modifier A/C assess bar quality separately.
        # Window count : bars since the most recent structural event (either type).
        # ======================================================================

        df['Prev_10_High'] = df['high'].shift(1).rolling(window=10).max()
        df['Prev_10_Low']  = df['low'].shift(1).rolling(window=10).min()

        df['Is_Breakout'] = df['close'] > df['Prev_10_High']

        # [PE-CAL-1 FIX §6.1] Profile B pullback zone widened: upper bound uses
        # EMA 21 + 0.5 ATR instead of ANCHOR (SMA 50) + 0.5 ATR. In a real trend,
        # EMA 21 is the natural pullback anchor -- the 0.5 ATR zone from SMA 50 is
        # too narrow for a separated MA stack. Profile A/C retain ANCHOR-based zone.
        _pb_upper = (df['EMA_21'] + (0.5 * df['ATRr_14'])) if p_code == "B" else (df['ANCHOR'] + (0.5 * df['ATRr_14']))
        df['Is_Pullback'] = (
                (df['close'] <= _pb_upper) &
                (df['close'] >= df['ANCHOR'])
        )

        if p_code == "A":
            df.loc[df.index[-1], 'Is_Breakout'] = False
            df.loc[df.index[-1], 'Is_Pullback'] = False

        # [PE-CAL-1 FIX §6.3] ADX threshold cross resets window for Profile B.
        # When ADX crosses above 20 (RESOLVING activation), the directional regime
        # is new -- the setup is not stale. Window freshness is measured from
        # regime change, not from the last price event.
        df['_Is_ADX_Cross'] = (df[adx_col] > 20) & (df[adx_col].shift(1) <= 20)

        # Window limits per profile  [MANDATE: DOC 2 SEC III]
        # A=4 hourly bars (VWAP resets daily -- natural staleness protection)
        # B=5 daily bars  (SMA 50 pullbacks develop over 3-7 days)
        # C=4 weekly bars [PE-CAL-1 §6.5: widened from 2 to ~1 month]
        window_limit  = 4 if p_code == "A" else (5 if p_code == "B" else 4)
        window_tail   = window_limit + 10  # lookback buffer -- always larger than the limit

        # [PE-CAL-1 §6.3] Include ADX cross as window event for Profile B
        recent_series = (df['Is_Breakout'] | df['Is_Pullback'] | (df['_Is_ADX_Cross'] if p_code == "B" else False))
        recent_events = (recent_series.iloc[:-1].tail(window_tail) if p_code == "A" else recent_series.tail(window_tail)).astype(bool).to_list()
        window_count  = recent_events[::-1].index(True) if any(recent_events) else 99  # 99 = sentinel: no valid window found

        # [PE-CAL-1] Identify what type of event reset the window for operator transparency.
        # Looks at the specific bar that triggered the reset and checks which flag was true.
        _window_reset_event = "NONE"
        if window_count != 99:
            _reset_series = recent_series.iloc[:-1].tail(window_tail) if p_code == "A" else recent_series.tail(window_tail)
            _reset_idx = _reset_series.index[-1 - window_count]  # index of the resetting bar
            _events = []
            if df.loc[_reset_idx, 'Is_Pullback']:
                _events.append("PULLBACK")
            if df.loc[_reset_idx, 'Is_Breakout']:
                _events.append("BREAKOUT")
            if p_code == "B" and df.loc[_reset_idx, '_Is_ADX_Cross']:
                _events.append("ADX_CROSS_20")
            _window_reset_event = " + ".join(_events) if _events else "UNKNOWN"

        # ======================================================================
        # VIOLATED STATE DETECTION  [MANDATE: DOC 2 SEC 4.1 / SEC VI.3]
        #
        # Doc 2 P026: Floor Violation = 1 to 3 consecutive bar closes BELOW the
        #             Structural Floor.
        # Doc 2 P075: Reclaim Trigger = (1) Previous 1-3 bars below floor;
        #             (2) CURRENT bar closes ABOVE floor.
        #
        # The logic is split into two independent checks:
        #   A) Is the CURRENT bar above or below the floor?
        #   B) How many PRIOR bars (k=2 onward) were consecutively below floor?
        #
        # This is the critical separation. The original loop started at k=1
        # (the current bar). When the current bar is above floor, that loop
        # would break immediately (consec_below=0) making is_reclaim impossible.
        # ======================================================================
        i0 = -2 if p_code == "A" else -1  # evaluated bar index (Profile A uses last completed bar)
        current_above_floor = df['close'].iloc[i0] >= df['ANCHOR'].iloc[i0]

        # [PE-29] Floor failure threshold scaled by profile bar frequency.
        # Profile A (hourly): 8 bars (~1 full session) before declaring structural break.
        # Profile B (daily):  4 bars (~1 week) -- original threshold, appropriate for daily.
        # Profile C (weekly): 4 bars (~1 month) -- 4 weeks is already substantial.
        # The violation range (below threshold) and lookback depth scale accordingly.
        _ff_threshold = 8 if p_code == "A" else 4
        _ff_lookback  = _ff_threshold + 1  # scan depth: threshold + 1 for boundary detection

        # Grace buffer: a bar must close more than 0.15 ATR below the floor to count
        # as a "below" bar. This prevents micro-wicks and hairline breaches from
        # triggering violated/failure states on stocks hugging their floor.
        grace = 0.15 * float(df['ATRr_14'].iloc[i0]) if not pd.isna(df['ATRr_14'].iloc[i0]) else 0

        if current_above_floor:
            # Current bar reclaimed. Count consecutive below-floor bars among
            # PRIOR bars (k=2 is the bar before current, k=3 is two bars ago...).
            consec_below = 0
            for offset in range(1, _ff_lookback):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    consec_below += 1
                else:
                    break  # Streak broken -- stop counting
            is_violated     = False                                        # Current bar is healthy
            is_reclaim      = (1 <= consec_below <= (_ff_threshold - 1))  # Prior bars below but under threshold = Reclaim
            is_floor_failure = (consec_below >= _ff_threshold)             # Structural failure
        else:
            # Current bar is below floor. Count the current streak including it.
            consec_below = 0
            for offset in range(0, _ff_lookback):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    consec_below += 1
                else:
                    break
            is_violated      = (1 <= consec_below <= (_ff_threshold - 1))  # Waiting for Reclaim
            is_reclaim       = False                                        # Current bar not above floor
            is_floor_failure = (consec_below >= _ff_threshold)              # Structural failure

        # ======================================================================
        # FLOOR FAILURE RECOVERY TRACKING  [3-BAR RECLAIM MANDATE]
        #
        # After a floor failure (threshold+ bars below), structural recovery requires
        # 3 consecutive closes above floor to reset the exit signal. This creates
        # symmetric conviction with the §X exit counter (3 bars to trigger exit,
        # 3 bars to confirm reclaim). Precedent: Floor Trader System requires
        # "price above both SMAs for at least three consecutive bars" to confirm
        # trend reclaim.
        #
        # Problem solved: the simple backward counter "forgets" a floor failure
        # after 2 reclaim bars (the below-floor bars shift out of the lookback
        # window). This deeper scan detects recent failures and re-asserts
        # is_floor_failure until 3 consecutive reclaim bars are confirmed.
        # ======================================================================
        _reclaim_run = 0  # Tracks consecutive above-floor bars for PE-25 messaging
        if current_above_floor:
            if is_floor_failure:
                # Original counter detected floor failure (4+ prior bars below).
                # Current bar is the FIRST reclaim bar.
                _reclaim_run = 1
            elif not is_violated:
                # No immediate failure detected by simple counter.
                # Scan deeper: count consecutive above-floor closes from i0 backward.
                for _r_off in range(0, _ff_threshold + 4):
                    if df['close'].iloc[i0 - _r_off] >= df['ANCHOR'].iloc[i0 - _r_off]:
                        _reclaim_run += 1
                    else:
                        break

                # If only 1-2 reclaim bars, check for floor failure behind them
                if 1 <= _reclaim_run <= 2:
                    _hist_below = 0
                    for _h_off in range(_reclaim_run, _reclaim_run + _ff_lookback):
                        _h_dist = df['ANCHOR'].iloc[i0 - _h_off] - df['close'].iloc[i0 - _h_off]
                        if _h_dist > grace:
                            _hist_below += 1
                        else:
                            break

                    if _hist_below >= _ff_threshold:
                        # Recent floor failure with insufficient reclaim — re-assert
                        is_floor_failure = True
                        is_reclaim = False
                        consec_below = _hist_below
                # _reclaim_run >= 3: floor failure fully resolved, no re-assertion

        # ======================================================================
        # METRICS PAYLOAD  [MANDATE: DOC 3 SEC 498 & DOC 8 SEC 466]
        # All values normalised to display currency (pence -> pounds for GBP).
        # ======================================================================

        floor_raw   = last['ANCHOR']
        floor_price = round(floor_raw / price_scaler, 2)
        hard_stop   = round(hard_stop_raw / price_scaler, 2)

        # Profile-specific derived metrics  [MANDATE: DOC 2 SEC 4.3]
        # [PE-26] Profit_Target_Synthetic for Profile B: Floor + 1.5 ATR.
        # A risk-calibrated intermediate profit objective for pullback entries.
        # Suppressed if price is already above it (target is behind current price).
        target_1_b  = round((floor_raw + (1.5 * atr_raw)) / price_scaler, 2) if p_code == "B" else None
        # [CONVEXITY] C-3 Synthetic target suppression (Redesign Proposal §6.2 / Execution Map §VI)
        # C-3 has open-ended reward. A fixed Floor + 1.5 ATR target would cap the right tail
        # and contradict the C-3 management regime. Suppress immediately.
        if _is_c3 and target_1_b is not None:
            target_1_b = None
            metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: C-3 open-ended reward -- no synthetic target"
        elif target_1_b is not None and target_1_b <= actual_price:
            target_1_b = None
            metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: price already above Floor + 1.5 ATR -- await pullback to floor"

        # Profile C Floor Proximity: % distance from the Weekly 200-SMA
        if p_code == "C":
            floor_prox_pct = round(
                abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100, 2
            )
        else:
            floor_prox_pct = None

        # Profile A floor is immutably VWAP -- Convexity Protocol is Profile B only.
        # p_code checks must come before is_resolving to prevent label contamination.
        anchor_label = (
            "VWAP (Baseline Floor)"              if p_code == "A" else
            "EMA 8 (Convexity Protocol)"         if (p_code == "B" and is_resolving and not is_trending and not is_etf) else
            "50-SMA (Baseline Floor)"            if p_code == "B" else
            "200-SMA (Baseline Floor)"
        )

        # Four distinct labels so the Operator is never misled:
        #   TRENDING   : ADX > 25 + full MA stack
        #   RESOLVING  : ADX > 20 + 3-bar slope
        #   MID-RANGE  : ADX < 20 OR MA squeeze  (true non-directional regime)
        #   AMBIGUOUS  : ADX > 20 but no protocol confirmed (MA stack broken /
        #                slope absent / ETF lock) -- different from MID-RANGE
        # [BUG #38 FIX] ETF Logic Lock forces is_trending/is_resolving to False,
        # causing the state chain to fall through to "AMBIGUOUS (MA STACK BROKEN)"
        # even when the MA stack is fully intact. Add explicit ETF states BEFORE the
        # AMBIGUOUS fallthrough so operators see the correct structural picture.
        engine_state = (
            "VIOLATED -- RECLAIM ACTIVE (STATE AMBIGUOUS)"  if (is_reclaim and not (_entry_trending or _entry_resolving)) else
            "VIOLATED -- RECLAIM ACTIVE"                    if is_reclaim   else
            "VIOLATED -- AWAITING RECLAIM"                  if is_violated  else
            "TRENDING"                                      if is_trending  else
            "RESOLVING"                                     if is_resolving else
            "MID-RANGE (ADX <20)"                           if adx_t < 20 else
            "MID-RANGE (MA SQUEEZE)"                          if ma_squeeze else
            "TRENDING (ETF -- BASELINE FLOOR ONLY)"         if (is_etf and ma_stack_full and adx_t > 20 and not ma_squeeze) else
            "RESOLVING (ETF -- BASELINE FLOOR ONLY)"        if (is_etf and adx_t >= 20) else
            "AMBIGUOUS (DOWNTREND -- ADX MEASURING BEARISH MOMENTUM)"  if _resolving_is_bearish else
            "AMBIGUOUS (MA STACK BROKEN)"                   if adx_t >= 25 else
            "AMBIGUOUS (ADX >20, No Protocol)"
        )

        metrics["Price"]             = round(actual_price, 2)
        metrics["Structural_Floor"]  = floor_price
        # Suppress Hard_Stop when it is above current price -- this occurs when price
        # has broken below the floor and the stop (anchored to floor - 1.5 ATR) is
        # now stale above entry. In this state Exit_Signal is true and the stop is
        # irrelevant; showing it above price is actively misleading to the Operator.
        if hard_stop < actual_price:
            metrics["Hard_Stop"]     = hard_stop
        else:
            metrics["Hard_Stop"]     = None
            metrics["Hard_Stop_Note"] = "SUPPRESSED: stop above current price -- floor already broken, Exit_Signal active"
        # --- SSG-001 METRICS ---
        metrics["Original_Hard_Stop"]   = round(_ssg_original_raw / price_scaler, 2) if _ssg_adjusted else None
        metrics["Stop_Adjusted_Flag"]   = _ssg_adjusted
        metrics["Stop_Adjusted_Reason"] = _ssg_reason
        metrics["ADV_20"]            = float(adv_20)
        metrics["ATR_Dist"]          = round(atr_dist, 2)
        metrics["Extension_Limit"]   = ext_limit   # [R-9] Profile/state-dependent ATR ceiling
        # Surface evaluation-rule context when live bar has GENUINELY recovered above floor
        # but floor failure is still active on completed bars. Without this note,
        # ATR_Dist > 0 and Exit_Signal = true appear contradictory to the operator.
        # Guard: also require last['close'] > last['ANCHOR'] -- prevents spurious note
        # when ATR_Dist is positive due to an anchor mismatch (e.g. ETF Profile A was
        # previously computing prox_anchor from SMA_200 rather than VWAP, yielding a
        # false positive ATR_Dist even when price was below the VWAP floor).
        _live_bar_above_floor = last['close'] >= last['ANCHOR']
        if round(atr_dist, 2) > 0 and (is_violated or is_floor_failure) and _live_bar_above_floor:
            metrics["ATR_Dist_Note"] = (
                f"LIVE BAR RECOVERY: current bar above floor ({round(last['close'] / price_scaler, 2)} > "
                f"{round(last['ANCHOR'] / price_scaler, 2)}) but floor "
                f"{'failure' if is_floor_failure else 'violation'} based on "
                f"{consec_below} completed bar(s) below. "
                f"Check Exit_Signal field for position management status."
            )
        # [BUG #39 FIX] ETF Profile B uses SMA_50 as proximity anchor (not EMA_21).
        # ETF Profile C uses SMA_200 (same as structural floor -- not EMA_21).
        # ETF cases must be evaluated BEFORE the generic p_code in ("B","C") branch
        # which previously caused ETF assets to display an incorrect anchor label.
        metrics["ATR_Dist_Anchor"]   = (
            "EMA_8"   if (p_code == "B" and is_resolving and not is_trending and not is_etf) else
            "SMA_50"  if (is_etf and p_code == "B") else   # ETF Profile B: SMA_50 anchor (immutable)
            "SMA_200" if (is_etf and p_code == "C") else   # ETF Profile C: SMA_200 anchor (same as floor)
            "SMA_200" if p_code == "C" else                 # [PE-CAL-1 §6.4] Profile C realigned to SMA_200
            "EMA_21"  if p_code == "B" else                 # Profile B TRENDING: EMA_21 anchor
            "VWAP"    if p_code == "A" else
            "SMA_200"
        )
        metrics["window_count"]      = int(window_count)
        metrics["Window_Limit"]      = window_limit   # [R-10] Profile-dependent: A=4, B=5, C=4 [PE-CAL-1]
        metrics["Window_Reset_Event"] = _window_reset_event  # [PE-CAL-1] What triggered the window: PULLBACK, BREAKOUT, ADX_CROSS_20
        metrics["Floor_Failure_Threshold"] = _ff_threshold  # [PE-29] Profile-dependent: A=8, B/C=4
        # [CONVEXITY] Write classification tag to metrics (Redesign Proposal §4.2 / Execution Map §VI)
        # When convexity_class is None (unclassified), no tag is written — backward compatible.
        if convexity_class is not None:
            metrics["Convexity_Class"] = convexity_class
        metrics["Anchor_Type"]       = "EMA_8" if (p_code == "B" and is_resolving and not is_trending and not is_etf) else "Standard"
        metrics["Anchor_Label"]      = anchor_label
        metrics["ADX"]               = round(adx_t, 2)
        metrics["DI_Plus"]           = round(di_plus, 2)
        metrics["DI_Minus"]          = round(di_minus, 2)
        metrics["Engine_State"]      = engine_state
        metrics["Conviction"]        = conviction_state
        metrics["Inst_Churn"]        = mod_d_state
        metrics["ADX_Accel"]         = adx_accel
        metrics["ADX_Accel_State"]   = adx_accel_state
        metrics["Vol_Confirm_Ratio"] = vol_confirm_ratio
        metrics["Vol_Confirm_State"] = vol_confirm_state
        metrics["Active_Modifiers"]  = ", ".join(active_mods) if active_mods else "None"
        resistance_display = round((df['high'].iloc[-12:-2].max() if p_code == "A" else df['high'].iloc[-11:-1].max()) / price_scaler, 2)
        # [BUG #42 FIX] When price is above the 10-bar resistance ceiling, the
        # resistance value is no longer a forward target -- it is a stale level
        # behind current price. Displaying it alongside a SUPPRESSED note creates
        # a direct contradiction in the payload (operator sees both the number and
        # the declaration that the number is suppressed). Null the value and set
        # a flag so the downstream R:R block can suppress RR_Target_Price and
        # Reward_Risk consistently (secondary inconsistency fix).
        _resistance_suppressed = resistance_display < actual_price
        if _resistance_suppressed:
            metrics["Resistance"]      = None
            # [PE-CAL-1] Context-aware messaging: when floor is broken, "await pullback"
            # is contradictory -- you can't pull back to a floor that's above you.
            if is_floor_failure or (last['close'] < floor_raw):
                metrics["Resistance_Note"] = "SUPPRESSED: price above 10-bar high but below structural floor -- resistance metric not meaningful in broken structure"
            else:
                metrics["Resistance_Note"] = "SUPPRESSED: price already above resistance -- no overhead reward ceiling; await pullback"
        else:
            metrics["Resistance"] = resistance_display
        metrics["EMA_8"]             = round(last['EMA_8']   / price_scaler, 2)
        metrics["EMA_21"]            = round(last['EMA_21']  / price_scaler, 2)
        # [BUG #44 FIX] GBP pence stocks (price_scaler=100) have ATR values in the
        # 1-5 pence range. Dividing by 100 and rounding to 2dp collapses the entire
        # value to 0.01 or 0.02 -- a single digit that loses all precision. The
        # operator then sees ATR=0.01 alongside ATR_Dist=-0.34 and concludes the
        # two figures are inconsistent, even though the underlying atr_raw is used
        # correctly and consistently throughout all internal computations (Hard_Stop,
        # ATR_Dist, grace buffer, extension limit). The fix is to display ATR with
        # 4dp for GBP stocks, producing e.g. 0.0133 instead of 0.01 -- enough
        # precision to verify ATR_Dist by mental arithmetic.
        _atr_display_dp = 4 if price_scaler == 100.0 else 2
        metrics["ATR"]               = round(atr_raw         / price_scaler, _atr_display_dp)
        # [PE-23 FIX] Guard SMA_200 against NaN. Profile A requests 3 months of hourly
        # bars (~410 bars), so SMA_200 usually has valid values. But for short-history
        # tickers (recently IPO'd, just above the 30-bar minimum), SMA_200 is entirely
        # NaN. round(NaN / price_scaler, 2) produces NaN, which causes json.dumps() to
        # emit a non-standard NaN literal that breaks strict JSON consumers downstream.
        if 'SMA_200' in df.columns and not pd.isna(last['SMA_200']):
            metrics["SMA_200"]       = round(last['SMA_200'] / price_scaler, 2)
        else:
            metrics["SMA_200"]       = None
        metrics["SMA_50"]            = round(last['SMA_50']  / price_scaler, 2)

        # Target_1 written after Exit Conditions block -- see line below exit_signal assignment.

        # Profile B Reward/Risk  [MANDATE: DOC 2 SEC 4.3 / audit parity with Profile A]
        # Reward = Resistance (10-bar consolidation high) - Price
        # Risk   = Price - Structural Floor (SMA_50)
        # Mirrors Profile A convention: risk measured to structural floor, not Hard_Stop.
        if p_code == "B":
            reward_b = resistance_raw - last['close']
            risk_b   = last['close']  - floor_raw
            # [CONVEXITY] C-3 Expectancy Gate bypass (Redesign Proposal §6.2 / Execution Map §VI)
            # C-3 has open-ended reward. Computing R:R against a fixed resistance level
            # treats the breakout as a range-bound trade, which contradicts the C-3 thesis.
            # Profit_Target is written as INFORMATIONAL (see Profit_Target_Role field).
            # Reward_Risk is suppressed — operator uses Risk_Per_Unit instead.
            if _is_c3:
                if _resistance_suppressed or (is_floor_failure or (last['close'] < floor_raw)):
                    metrics["Profit_Target"]        = None
                    metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                    metrics["Reward_Risk"]           = None
                    metrics["Reward_Risk_Note"]      = "BYPASSED: C-3 open-ended reward -- R:R against fixed resistance not meaningful"
                else:
                    metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
                    metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                    metrics["Reward_Risk"]           = None
                    metrics["Reward_Risk_Note"]      = (
                        f"BYPASSED: C-3 open-ended reward. Resistance ({round(resistance_raw / price_scaler, 2)}) "
                        f"is INFORMATIONAL only. Use Risk_Per_Unit for risk assessment."
                    )
            # [BUG #42 FIX -- secondary] When resistance is suppressed (price above
            elif _resistance_suppressed:
                metrics["Profit_Target"]        = None
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = None
                # [PE-CAL-1] Context-aware: distinguish "extended above resistance" from
                # "floor broken, resistance metric meaningless"
                if is_floor_failure or (last['close'] < floor_raw):
                    metrics["Reward_Risk_Note"] = (
                        f"UNDEFINED: structural floor broken (price {round(actual_price, 2)} below floor {floor_price}). "
                        f"10-bar high ({resistance_display}) is not a valid reward target in broken structure."
                    )
                else:
                    metrics["Reward_Risk_Note"] = (
                        f"UNDEFINED: price ({round(actual_price, 2)}) above resistance ceiling ({resistance_display}) -- "
                        f"no reward target available. Await pullback to floor ({floor_price}) before re-evaluating."
                    )
            elif pd.isna(risk_b) or risk_b < 0:
                # [PE-10 FIX] Null Profit_Target alongside Reward_Risk when price is
                # below the structural floor. A target price displayed next to a null R:R
                # with "UNDEFINED" note is a payload contradiction -- the target has no
                # meaning without a valid ratio. Resistance already carries the value for
                # informational purposes; Profit_Target is strictly an R:R output field.
                metrics["Profit_Target"]        = None
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = None
                metrics["Reward_Risk_Note"] = "UNDEFINED: price below structural floor"
            elif risk_b == 0:
                metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = 9999.0
                metrics["Reward_Risk_Note"] = "FLOOR_EXACT: price at SMA_50; risk denominator = 0; R:R treated as maximal"
            else:
                metrics["Profit_Target"]        = round(resistance_raw / price_scaler, 2)
                metrics["Profit_Target_Source"]  = "10_Bar_Resistance"
                metrics["Reward_Risk"]           = round(reward_b / risk_b, 2)

        if floor_prox_pct is not None:
            metrics["Floor_Prox_Pct"] = float(floor_prox_pct)     # Profile C only

        # [PE-26] Profile C: no profit targets per Doc 2 §4.3. Explicit null fields
        # ensure the Operator always sees a consistent Profit_Target / Source pair.
        if p_code == "C":
            metrics["Profit_Target"]        = None
            metrics["Profit_Target_Source"]  = "None"

        # [CONVEXITY] Profit_Target_Role (Redesign Proposal §6.2 / Execution Map §VI)
        # Distinguishes prescriptive exits from informational levels.
        #   PRESCRIPTIVE (C-1/C-2): Operator treats profit target as a mechanical exit.
        #   INFORMATIONAL (C-3):    Operator sees the level but does not exit mechanically.
        # When convexity_class is None, field is omitted — backward compatible.
        if convexity_class is not None:
            metrics["Profit_Target_Role"] = "INFORMATIONAL" if _is_c3 else "PRESCRIPTIVE"

        # [CONVEXITY] Risk_Per_Unit (Redesign Proposal §6.2 / Execution Map §VI)
        # For C-3 RESOLVING entries, reward is structurally undefined (open-ended).
        # Risk_Per_Unit = (price − EMA 8) / ATR measures the operator's actual risk
        # exposure without requiring a bounded reward target.
        if _is_c3 and is_resolving and not is_trending and p_code == "B":
            _ema8_risk = last['close'] - last['EMA_8']
            if not pd.isna(_ema8_risk) and atr_raw > 0:
                metrics["Risk_Per_Unit"] = round(_ema8_risk / atr_raw, 2)

        if p_code == "A":
            vwap_col = [c for c in df.columns if 'VWAP' in c][0]
            metrics["VWAP"] = round(last[vwap_col] / price_scaler, 2)

        # ======================================================================
        # SECTION X: EXIT CONDITION SIGNALS  [MANDATE: DOC 2 TABLE 1]
        # Computed and surfaced in metrics for the Orchestrator and Operator.
        # These are POSITION MANAGEMENT signals, not entry gates.
        #
        # Profile A: Price falls below established Hourly Low OR
        #            1-3 consecutive hourly closes below VWAP.
        # Profile B: Daily close < Daily 50-SMA OR
        #            Daily close < EMA 8 (if Convexity Protocol active).
        # Profile C: Weekly close < Weekly 200-SMA.
        # ======================================================================

        # All Exit_Signal values cast to native Python types.
        # pandas comparisons return numpy.bool_ which json.dumps cannot serialize.
        # [PE-28] Exit_Signal graduated from boolean to "WARNING" / "EXIT" / false.
        #   WARNING: Early deterioration -- single trigger. Tighten awareness, no
        #            mechanical action mandated. R:R and Profit_Target remain visible.
        #   EXIT:    Structural break -- multiple triggers or sustained VWAP violation.
        #            Full mechanical exit mandate. R:R and Profit_Target suppressed.
        if p_code == "A":
            est_hourly_low_raw = float(df['low'].iloc[-12:-2].min())
            exit_a_low    = bool(last['close'] < est_hourly_low_raw)
            # [PE-27] Surface computed reference so operator can verify the trigger.
            metrics["Established_Hourly_Low"] = round(est_hourly_low_raw / price_scaler, 2)
            # [MANDATE: DOC 2 SEC X] 3 consecutive hourly closes STRICTLY below VWAP.
            # This counter is DECOUPLED from the entry-side consec_below counter
            # (which applies the §4.1 grace buffer of 0.15 ATR). The grace buffer
            # exists to prevent micro-wicks from triggering false violated/reclaim
            # states on the ENTRY side. On the EXIT side, the risk asymmetry is
            # inverted: the operator already holds the position, and sustained closes
            # below VWAP -- even by small amounts -- represent structural deterioration.
            # §X defines "closes below VWAP" with no grace qualifier. Applying the
            # entry-side grace here would delay exit signals on deteriorating positions.
            # [R-2 DESIGN NOTE] Exit counter intentionally uses NO grace buffer (Doc 2 §X).
            # Entry counter uses 0.15 ATR grace (Doc 2 §4.1). These can disagree on bar counts.
            # PE-25 override ensures is_floor_failure always takes precedence when entry-side
            # detects structural break, regardless of exit counter state.
            _exit_consec = 0
            for _eoff in range(0, 5):  # [R-3 FIX] Was range(0,4) -- now matches entry counter depth
                if df['close'].iloc[i0 - _eoff] < df['ANCHOR'].iloc[i0 - _eoff]:
                    _exit_consec += 1
                else:
                    break
            exit_a_vwap   = bool(_exit_consec >= 3)
            # [PE-28] Graduated severity:
            #   - VWAP 3-bar alone        → EXIT (sustained structural deterioration)
            #   - Both triggers            → EXIT
            #   - Hourly low breach alone  → WARNING (could be single volatile bar)
            #   - Neither                  → false
            _exit_triggers = []
            if exit_a_low:
                _exit_triggers.append("Hourly_Low_Breach")
            if exit_a_vwap:
                _exit_triggers.append("VWAP_3Bar_Violation")
            if exit_a_vwap:
                exit_signal = "EXIT"
            elif exit_a_low:
                exit_signal = "WARNING"
            else:
                exit_signal = False
            metrics["Exit_Signal"]       = exit_signal
            metrics["Exit_Triggers"]     = _exit_triggers if _exit_triggers else "None"
            metrics["Exit_VWAP_Counter"] = f"{min(_exit_consec, 3)}/3"
            metrics["Exit_Reason"]       = (
                f"VWAP Violation ({_exit_consec} consecutive bar(s) below floor -- strict Sec X counter)"
                if exit_a_vwap else
                "Close below established Hourly Low" if exit_a_low
                else "None"
            )
        elif p_code == "B":
            exit_b_std   = bool(last['close'] < last['SMA_50'])
            exit_b_conv  = bool(is_resolving and not is_trending and (last['close'] < last['EMA_8']))
            # [PE-28] Profile B graduation:
            #   - Close < SMA_50           → EXIT (structural floor break)
            #   - Close < EMA_8 only       → WARNING (Convexity tightening, floor intact)
            #   - Neither                  → false
            _exit_triggers = []
            if exit_b_std:
                _exit_triggers.append("SMA_50_Breach")
            if exit_b_conv:
                _exit_triggers.append("EMA_8_Convexity_Breach")
            if exit_b_std:
                exit_signal = "EXIT"
            elif exit_b_conv:
                # [CONVEXITY] C-3 EMA 8 EXIT escalation (Redesign Proposal §6.2 / Execution Map §VI)
                # For C-3 positions, EMA 8 IS the structural floor. A breach is thesis
                # invalidation, not a caution flag. Escalate from WARNING → EXIT.
                # For C-1/C-2, EMA 8 breach remains WARNING (floor intact at SMA 50).
                exit_signal = "EXIT" if _is_c3 else "WARNING"
            else:
                exit_signal = False
            metrics["Exit_Signal"]       = exit_signal
            metrics["Exit_Triggers"]     = _exit_triggers if _exit_triggers else "None"
            metrics["Exit_Reason"]       = (
                "Close below EMA 8 (Convexity active) -- C-3 EXIT: thesis invalidation" if exit_b_conv and _is_c3 and not exit_b_std else
                "Close below EMA 8 (Convexity active)" if exit_b_conv and not exit_b_std else
                "Close below 50-SMA" if exit_b_std
                else "None"
            )
        elif p_code == "C":
            exit_c  = bool(last['close'] < last['SMA_200'])
            # Profile C has a single structural trigger -- always EXIT when breached.
            exit_signal  = "EXIT" if exit_c else False
            metrics["Exit_Signal"]       = exit_signal
            metrics["Exit_Triggers"]     = ["SMA_200_Breach"] if exit_c else "None"
            metrics["Exit_Reason"]       = "Close below 200-SMA" if exit_c else "None"

        # [PE-25 FIX] Floor failure override: structural break (threshold+ consecutive bars below
        # floor) cannot be reset by a single reclaim bar. The exit-side counter starts at
        # the current bar and breaks immediately when it's above floor, yielding
        # exit_signal = False even during confirmed structural failure. This override
        # ensures is_floor_failure (from the entry-side counter) always takes precedence.
        # [3-BAR RECLAIM MANDATE] _reclaim_run tracks recovery progress (1/3, 2/3).
        # After 3 consecutive closes above floor, is_floor_failure resets and this
        # block no longer fires — exit_signal returns to normal profile logic.
        if is_floor_failure and exit_signal != "EXIT":
            exit_signal = "EXIT"
            metrics["Exit_Signal"] = "EXIT"
            # [PE-28] Append structural trigger to existing triggers list
            _existing_triggers = metrics.get("Exit_Triggers", [])
            if isinstance(_existing_triggers, str):
                _existing_triggers = []
            _existing_triggers.append("Floor_Failure_Override")
            metrics["Exit_Triggers"] = _existing_triggers
            metrics["Exit_Reason"] = (
                f"FLOOR FAILURE OVERRIDE: {consec_below} consecutive completed bars below floor. "
                f"Reclaim progress: {_reclaim_run}/3 bars above floor. "
                f"3 consecutive closes above floor required to reset structural break."
            )
            metrics["Floor_Failure_Reclaim"] = f"{_reclaim_run}/3"

        # [BUG #33 FIX -- RELOCATED] Write Profit_Target_Synthetic here, after exit_signal
        # is assigned for all three profiles. The early suppression block (price > target)
        # ran before exit_signal existed, causing UnboundLocalError on Profile B/C runs.
        # Both suppression conditions are now evaluated in correct execution order:
        #   1. Price > Profit_Target_Synthetic -- handled at computation site
        #   2. Exit_Signal = "EXIT"            -- handled here, post exit_signal assignment
        # [PE-28] Suppression only on EXIT. WARNING preserves forward metrics.
        if target_1_b is not None and exit_signal == "EXIT":
            target_1_b = None
            metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: Exit_Signal EXIT -- floor broken, no entry context"
        if target_1_b is not None:
            metrics["Profit_Target_Synthetic"] = target_1_b   # Profile B only: Floor + 1.5 ATR

        # [BUG #PE-7 FIX -- RELOCATED] Suppress Reward_Risk and Profit_Target when
        # Exit_Signal = EXIT. Moved here from after the Expectancy Gate so it fires
        # BEFORE the Floor Violation Pre-Check early returns. Previously, Pre-Check
        # returns bypassed the downstream PE-7 block, leaking unscrubbed R:R into
        # the payload (Profile B: stale Phase 1.5 R:R; Profile A: unaffected since
        # Expectancy Gate runs after Pre-Check).
        # Principle: no forward entry metrics when the structural floor is violated.
        # Same relocation pattern as Bug #33 (Profit_Target_Synthetic).
        # [PE-28] WARNING preserves R:R and Profit_Target -- operator needs context.
        if exit_signal == "EXIT" and metrics.get("Reward_Risk") is not None:
            metrics["Reward_Risk"]      = None
            metrics["Profit_Target"]    = None
            metrics["Reward_Risk_Note"] = (
                f"SUPPRESSED: Exit_Signal EXIT -- floor violated "
                f"({metrics.get('Exit_Reason', 'structural break')}). "
                f"No entry context. Await confirmed close above floor for reclaim evaluation."
            )

        # ======================================================================
        # TREND HEALTH SCORE [MODULE G]
        # Composite 0-100 metric from four sub-scores. Read-only — does not
        # alter any gate, exit, or verdict. All inputs are already in local
        # variables at this point. See TBS_Module_G_Trend_Health_Score_v1.docx.
        # ======================================================================
        def _clamp(v, lo, hi): return max(lo, min(hi, v))

        # Component 1: Floor Buffer (ATR distance price → structural floor)
        _fb_atr = (last['close'] - floor_raw) / atr_raw if atr_raw > 0 else 0
        _fb_max = {"A": 2.0, "B": 3.0, "C": 5.0}.get(p_code, 3.0)
        _fb = _clamp(_fb_atr / _fb_max, 0, 1) * 100 if _fb_atr > 0 else 0

        # Component 2: Directional Momentum (ADX strength + DI spread)
        _adx_s = _clamp((adx_t - 15) / 30, 0, 1)
        _di_s  = _clamp((di_plus - di_minus) / 20, 0, 1)
        _dm    = (_adx_s * 0.6 + _di_s * 0.4) * 100

        # Component 3: Trend Age (bars since window reset — window_count IS the age)
        _ta_max  = {"A": 30, "B": 80, "C": 60}.get(p_code, 80)
        _ta_bars = window_count if window_count != 99 else _ta_max
        _ta      = _clamp(1 - (_ta_bars / _ta_max), 0, 1) * 100

        # Component 4: Structure Quality (MA stack integrity + EMA separation)
        _stk = ((15 if last['close'] > last['EMA_8']  else 0)
                + (15 if last['EMA_8']  > last['EMA_21'] else 0)
                + (10 if last['EMA_21'] > last['SMA_50'] else 0)
                + (10 if ('SMA_200' in df.columns and not pd.isna(last['SMA_200'])
                          and last['SMA_50'] > last['SMA_200']) else 0))
        _ema_gap = abs(last['EMA_8'] - last['EMA_21']) / atr_raw if atr_raw > 0 else 0
        _sq = _stk + _clamp(_ema_gap / 1.0, 0, 1) * 50

        # Weighted composite — convexity-aware
        if _is_c3:
            _ths = _fb * 0.25 + _dm * 0.25 + _ta * 0.20 + _sq * 0.30
        else:
            _ths = _fb * 0.40 + _dm * 0.25 + _ta * 0.15 + _sq * 0.20

        metrics['Trend_Health_Score'] = round(_ths, 1)
        metrics['THS_Label'] = (
            'STRONG' if _ths >= 80 else 'HEALTHY' if _ths >= 60
            else 'CAUTION' if _ths >= 40 else 'WEAK' if _ths >= 20 else 'CRITICAL')
        metrics['THS_Floor_Buffer']   = round(_fb, 1)
        metrics['THS_Dir_Momentum']   = round(_dm, 1)
        metrics['THS_Trend_Age']      = round(_ta, 1)
        metrics['THS_Structure']      = round(_sq, 1)
        metrics['Trend_Age_Bars']     = int(_ta_bars)

        # ======================================================================
        # ENG-001: ROUND NUMBER PROXIMITY DIAGNOSTIC  [Amendment ENG-001]
        # Placed here -- after the core metrics payload is fully populated
        # (Hard_Stop, Structural_Floor always set by this point; Profit_Target
        # set for Profile B in the R:R block above, None for A/C until later)
        # -- and BEFORE all gate evaluation so that every return path (PASS
        # or HALT) carries the RN fields. metrics.get() gracefully returns
        # None for Profit_Target on paths where it has not yet been written
        # (Profile A Expectancy Gate runs later; those HALT paths correctly
        # surface None for RN_Target_Proximity).
        # NON-GATE: informational only. No verdict or gate impact.
        # ======================================================================
        _rn_target = metrics.get("Profit_Target")
        metrics["RN_Target_Proximity"] = (
            _check_round_number_proximity(_rn_target) if _rn_target is not None else None
        )
        _rn_stop = metrics.get("Hard_Stop")
        metrics["RN_Stop_Proximity"] = (
            _check_round_number_proximity(_rn_stop) if _rn_stop is not None else "CLEAR"
        )
        metrics["RN_Floor_Proximity"] = _check_round_number_proximity(
            metrics.get("Structural_Floor")
        )

        # ======================================================================
        # PHASE 1.5: CONTEXT DATA FETCH  [MANDATE: DOC 2 SEC 4.3 / P032]
        # df_ctx is fetched here -- BEFORE the Expectancy Gate -- so the daily
        # Consolidation High (10-bar daily Focus Window) is available for
        # Profile A reward measurement. Chart rendering happens in Phase 2.
        # ======================================================================

        ctx_map          = {"A": ("1 day", "12 M"), "B": ("1 week", "5 Y"), "C": ("1 month", "20 Y")}
        ctx_res, ctx_dur = ctx_map[p_code]
        ctx_bars         = ib.reqHistoricalData(contract, '', ctx_dur, ctx_res, 'TRADES', True)
        df_ctx           = None
        if ctx_bars:
            df_ctx = util.df(ctx_bars)
            df_ctx.set_index('date', inplace=True)
            df_ctx.index = pd.to_datetime(df_ctx.index)
            df_ctx.sort_index(inplace=True)
            for ln in [8, 21]:   df_ctx.ta.ema(length=ln, append=True)
            for ln in [50, 200]: df_ctx.ta.sma(length=ln, append=True)
            # [PE-20 FIX] Compute Volume SMA 9 on context data so the Context Chart
            # can render the overlay. Without this, the Analyst cannot visually verify
            # climax conditions (Volume > 2x SMA 9) at the higher timeframe per
            # Doc 4 §I HITL protocol.
            df_ctx.ta.sma(close=df_ctx['volume'], length=9, append=True, col_names=('vol_sma_9',))

        # ======================================================================
        # PHASE 2: CHART RENDERING -- PRIMARY + CONTEXT
        # [MANDATE: DOC 4 SEC II] Triple-View = Primary + Context + Focus
        # Rendered here -- AFTER context data fetch, BEFORE all gate evaluation --
        # so charts exist for every outcome: PASS, HALT, and error paths alike.
        # Focus chart deferred until after confirmed PASS (Phase 4B).
        # ======================================================================

        primary_path = os.path.join(chart_dir, f"{clean_ticker}_primary.png")
        _build_primary_chart(
            df, p_code, profile, clean_ticker, adx_col, dmp_col, dmn_col
        ).write_image(primary_path)

        ctx_path = None
        if df_ctx is not None:
            ctx_path = os.path.join(chart_dir, f"{clean_ticker}_context.png")
            _build_context_chart(df_ctx, p_code, profile, clean_ticker).write_image(ctx_path)

        chart_ref = f"Primary: {primary_path}" + (f" | Context: {ctx_path}" if ctx_path else "")

        # ======================================================================
        # CONTEXT REGIME GATE [CRG-1]  [MANDATE: DOC 2 AMENDMENT]
        #
        # Profile A only. Verifies the daily (Context) structural regime before
        # any PASS verdict can be issued. Two independent conditions:
        #   1. Golden Cross:  Daily SMA 50 > Daily SMA 200
        #   2. Secular Floor: Daily Close  > Daily SMA 200
        #
        # If either fails → Hard HALT. If df_ctx unavailable or SMA columns
        # are NaN → HALT (Ambiguity Clause §XI: incomplete data → DO NOTHING).
        #
        # Fires after Phase 2 (charts exist for HALT diagnostic) and before
        # Gate 0 / Floor Violation Pre-Check. All execution-chart analysis
        # is meaningless when the higher-timeframe regime is bearish.
        #
        # Metrics: Context_Golden_Cross (bool) and Context_Price_vs_SMA200
        # (float) are written on ALL Profile A evaluations for auditability.
        # ======================================================================
        if p_code == "A":
            if (df_ctx is not None
                    and 'SMA_50' in df_ctx.columns and 'SMA_200' in df_ctx.columns
                    and not pd.isna(df_ctx['SMA_50'].iloc[-1])
                    and not pd.isna(df_ctx['SMA_200'].iloc[-1])):
                _ctx_last = df_ctx.iloc[-1]
                _crg_golden_cross    = bool(_ctx_last['SMA_50'] > _ctx_last['SMA_200'])
                _crg_price_vs_sma200 = round(float(_ctx_last['close'] - _ctx_last['SMA_200']) / price_scaler, 2)
                metrics["Context_Golden_Cross"]    = _crg_golden_cross
                metrics["Context_Price_vs_SMA200"] = _crg_price_vs_sma200
                # [ENG-005 FIX] Context_SMA200 was written raw (pence for LSE equities)
                # while all other Operator-facing price metrics divide by price_scaler.
                # Apply the same scaling so Context_SMA200 displays in GBP, matching
                # SMA_200 / Price / Floor / Stop etc. in the payload.
                metrics["Context_SMA200"]          = round(float(_ctx_last['SMA_200']) / price_scaler, 2)

                _crg_failures = []
                if not _crg_golden_cross:
                    _crg_failures.append("Daily Golden Cross absent")
                if _ctx_last['close'] <= _ctx_last['SMA_200']:
                    _crg_failures.append("Price below Daily SMA 200")
                if _crg_failures:
                    return "HALT", (
                        f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED (Profile A): {' + '.join(_crg_failures)}. "
                        f"Hourly execution requires daily structural uptrend. "
                        f"Mandate: asset disqualified until daily regime recovers."
                    ), metrics
            else:
                # df_ctx unavailable or SMA columns NaN -- cannot verify regime
                metrics["Context_Golden_Cross"]    = None
                metrics["Context_Price_vs_SMA200"] = None
                metrics["Context_SMA200"]          = None
                return "HALT", (
                    "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: Insufficient daily data for SMA 200 computation. "
                    "Cannot verify structural regime."
                ), metrics

        # ======================================================================
        # CONTEXT REGIME GATE [CRG-2]  [MANDATE: DOC 2 AMENDMENT / CRG-2 SPEC v1.1]
        #
        # Profile B only. Verifies the weekly (Context) structural regime before
        # any PASS verdict can be issued. Single condition:
        #   1. Weekly SMA 50 Rising: current week SMA 50 > prior week SMA 50
        #
        # If weekly SMA 50 is declining or flat → Hard HALT.
        # If df_ctx unavailable or SMA 50 column NaN → HALT (Ambiguity Clause
        # §XI: incomplete data → DO NOTHING).
        #
        # Fires after CRG-1 (Profile A gate) and before Gate 0 (Liquidity).
        # All execution-chart analysis is meaningless when the higher-timeframe
        # intermediate trend is deteriorating.
        #
        # Metrics: Context_Weekly_SMA50_Slope (float), Context_Weekly_SMA50_Rising
        # (bool), Context_Weekly_SMA50 (float) — written on ALL Profile B
        # evaluations for auditability.
        # ======================================================================
        if p_code == "B":
            if (df_ctx is not None
                    and len(df_ctx) >= 2
                    and 'SMA_50' in df_ctx.columns):
                current_weekly_sma50 = df_ctx['SMA_50'].iloc[-1]
                prior_weekly_sma50   = df_ctx['SMA_50'].iloc[-2]

                if pd.isna(current_weekly_sma50) or pd.isna(prior_weekly_sma50):
                    metrics["Context_Weekly_SMA50_Slope"]  = None
                    metrics["Context_Weekly_SMA50_Rising"] = None
                    metrics["Context_Weekly_SMA50"]        = None
                    return "HALT", (
                        "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                        "Insufficient weekly data for SMA 50 slope computation. "
                        "Cannot verify structural regime."
                    ), metrics

                weekly_sma50_rising = bool(current_weekly_sma50 > prior_weekly_sma50)
                slope_value = round((current_weekly_sma50 - prior_weekly_sma50) / price_scaler, 2)

                metrics["Context_Weekly_SMA50_Slope"]  = slope_value
                metrics["Context_Weekly_SMA50_Rising"] = weekly_sma50_rising
                metrics["Context_Weekly_SMA50"]        = round(current_weekly_sma50 / price_scaler, 2)

                if not weekly_sma50_rising:
                    return "HALT", (
                        f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED "
                        f"(Profile B): Weekly SMA 50 declining (slope: {slope_value}). "
                        f"Intermediate-term trend not confirmed. Daily execution requires "
                        f"weekly structural improvement. Mandate: asset disqualified until "
                        f"weekly SMA 50 turns positive."
                    ), metrics
            else:
                # df_ctx unavailable or < 2 bars or SMA_50 column missing
                metrics["Context_Weekly_SMA50_Slope"]  = None
                metrics["Context_Weekly_SMA50_Rising"] = None
                metrics["Context_Weekly_SMA50"]        = None
                return "HALT", (
                    "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                    "Insufficient weekly data for SMA 50 computation. "
                    "Cannot verify structural regime."
                ), metrics

        # Gate 0 -- Liquidity fast-path  [Doc 2 Sec.II / Doc 8 Sec.II-IV]
        # Must fire BEFORE the floor pre-check so illiquid tickers never surface
        # floor-failure diagnostics (which would mask the true rejection reason).
        # [PE-4] LSE ETFs trade lower on-exchange volume but are backed by market
        # makers arbitraging against the underlying index. $5M threshold (same as
        # equities) filters genuinely illiquid products while admitting established
        # Vanguard/iShares UCITS ETFs. US ETFs retain the $50M threshold.
        _adv_limit_early = 5_000_000 if _is_lse_etf else (50_000_000 if is_etf else 5_000_000)
        if not pd.isna(adv_20) and adv_20 < _adv_limit_early:
            return "HALT", f"REJECT (reason: LIQUIDITY FAILED). Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${_adv_limit_early/1e6:.0f}M)", metrics

        # --- FLOOR VIOLATION PRE-CHECK ---
        # Must run BEFORE the Expectancy gate (which computes risk_a = price - VWAP
        # and fires a confusing "floor integrity failure" when price < VWAP).
        # Any broken-floor state is caught here with the correct diagnostic.
        # [R-1 FIX] Pre-check now uses Profile A's i0=-2 offset to evaluate the same
        # bar window as the main check. Previously used df.iloc[-1 - offset] which was
        # shifted by 1 bar for Profile A, causing potential disagreement on floor state.
        if atr_raw > 0:
            _precheck_i0 = -2 if p_code == "A" else -1  # [R-1] Match main check's i0
            floor_dist_pre = (df['close'].iloc[_precheck_i0] - df['ANCHOR'].iloc[_precheck_i0]) / atr_raw
            grace_pre = 0.15 * atr_raw
            consec_pre = 0
            for offset in range(1, _ff_lookback):
                bar_dist = df.iloc[_precheck_i0 - offset]['ANCHOR'] - df.iloc[_precheck_i0 - offset]['close']
                if bar_dist > grace_pre:
                    consec_pre += 1
                else:
                    break
            _precheck_current_above = df['close'].iloc[_precheck_i0] >= df['ANCHOR'].iloc[_precheck_i0]
            is_floor_failure_pre = consec_pre >= _ff_threshold
            is_violated_pre      = 1 <= consec_pre <= (_ff_threshold - 1)
            is_reclaim_pre       = is_violated_pre and _precheck_current_above
            if is_floor_failure_pre:
                # [PE-25 COMPLEMENT + 3-BAR RECLAIM] Set Exit_Signal and show
                # reclaim progress. Current bar above floor = 1st reclaim bar.
                # [PE-28] Graduated: floor failure is always EXIT severity.
                _pre_reclaim = 1 if _precheck_current_above else 0
                metrics["Exit_Signal"] = "EXIT"
                metrics["Exit_Triggers"] = ["Floor_Failure_Override"]
                metrics["Exit_Reason"] = (
                    f"FLOOR FAILURE OVERRIDE: {consec_pre} consecutive bars below floor. "
                    f"Reclaim progress: {_pre_reclaim}/3 bars above floor. "
                    f"3 consecutive closes above floor required to reset structural break."
                )
                metrics["Floor_Failure_Reclaim"] = f"{_pre_reclaim}/3"
                return "HALT", (
                        f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE{' RECOVERY' if _pre_reclaim > 0 else ''}: "
                        f"{consec_pre} consecutive bars below Floor. "
                        + (f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                           if _pre_reclaim > 0 else "Structural break.")
                ), metrics

            # [3-BAR RECLAIM MANDATE -- PRE-CHECK DEEP SCAN]
            # After 2 reclaim bars, the simple backward counter no longer detects
            # the floor failure (below-floor bars shifted out of lookback window).
            # Scan deeper to find recent failure behind the reclaim streak.
            if not is_floor_failure_pre and _precheck_current_above and not is_violated_pre:
                _pre_reclaim = 0
                for _pr_off in range(0, _ff_threshold + 4):
                    if df['close'].iloc[_precheck_i0 - _pr_off] >= df['ANCHOR'].iloc[_precheck_i0 - _pr_off]:
                        _pre_reclaim += 1
                    else:
                        break
                if 1 <= _pre_reclaim <= 2:
                    _pre_hist = 0
                    for _ph_off in range(_pre_reclaim, _pre_reclaim + _ff_lookback):
                        _ph_dist = df['ANCHOR'].iloc[_precheck_i0 - _ph_off] - df['close'].iloc[_precheck_i0 - _ph_off]
                        if _ph_dist > grace_pre:
                            _pre_hist += 1
                        else:
                            break
                    if _pre_hist >= _ff_threshold:
                        metrics["Exit_Signal"] = "EXIT"
                        metrics["Exit_Triggers"] = ["Floor_Failure_Override"]
                        metrics["Exit_Reason"] = (
                            f"FLOOR FAILURE OVERRIDE: {_pre_hist} consecutive bars below floor. "
                            f"Reclaim progress: {_pre_reclaim}/3 bars above floor. "
                            f"3 consecutive closes above floor required to reset structural break."
                        )
                        metrics["Floor_Failure_Reclaim"] = f"{_pre_reclaim}/3"
                        return "HALT", (
                            f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE RECOVERY: {_pre_hist} bars below Floor. "
                            f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                        ), metrics

            if is_violated_pre and not is_reclaim_pre:
                return (
                    "HALT",
                    f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: {consec_pre} bar(s) below Floor ({round(last['ANCHOR'] / price_scaler, 2)}). "
                    f"Current bar has NOT reclaimed (Close {round(last['close'] / price_scaler, 2)} < Floor). "
                    f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
                    f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_pre}/3 bars).",
                    metrics
                )
            if floor_dist_pre < -0.15 and not is_violated_pre:
                return "HALT", f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist_pre):.2f} ATR below Floor.", metrics

        # ======================================================================
        # PROFILE A: EXPECTANCY GATE  [MANDATE: DOC 2 SEC 4.3 / P032 / P038]
        # Mandatory 1:2 reward-to-risk gate for ALL Profile A PASS verdicts.
        # Applied here -- BEFORE Phase 4 -- so it covers Pullback, Breakout,
        # AND Reclaim paths equally. No Profile A trade bypasses this gate.
        #
        #   Reward = Consolidation High - Current Price
        #   Risk   = Current Price - Structural Floor
        #   Gate   = Reward >= 2.0 x Risk
        # ======================================================================

        if p_code == "A":
            # Reward measured against 10-bar DAILY high from Context Chart
            # [MANDATE: DOC 2 SEC 4.3 P032] -- swing trade targets daily structure,
            # not the narrow 10-bar hourly ceiling.
            if df_ctx is not None and len(df_ctx) >= 11:
                cons_high_raw = df_ctx['high'].iloc[-11:-1].max()
                # Edge case: price has already broken above the daily 10-bar range.
                # The daily high is now a stale floor-level -- fall back to the
                # hourly resistance (nearest structural ceiling above current price).
                if cons_high_raw < last['close']:
                    cons_high_raw = resistance_raw
                    metrics["Profit_Target_Source"] = "HOURLY_RESISTANCE (price above daily range)"
                else:
                    metrics["Profit_Target_Source"] = "DAILY_CTX"
            else:
                # Fallback to hourly if context data unavailable -- conservative
                cons_high_raw = df['high'].iloc[-12:-2].max()
                metrics["Profit_Target_Source"] = "FALLBACK_HOURLY (context data unavailable)"
            reward_a       = (cons_high_raw - last['close'])
            risk_a         = (last['close'] - last['ANCHOR'])   # Doc 2 P032: risk = distance to Structural Floor
            metrics["Cons_High"]   = round(cons_high_raw / price_scaler, 2)
            # Grace buffer: price within 0.15 ATR below floor is floor-hugging, not a breach.
            # Clamp risk_a to 0 in this zone (treated as floor-exact entry).
            _exp_grace = 0.15 * atr_raw if not pd.isna(atr_raw) and atr_raw > 0 else 0
            if pd.isna(risk_a):
                return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid Reward/Risk: risk_a is NaN.", metrics
            if risk_a < -_exp_grace:
                # Price is materially below VWAP floor -- genuine integrity failure.
                return "HALT", f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: price {round(last['close'] / price_scaler, 2)} is {abs(risk_a / atr_raw):.2f} ATR below floor ({round(last['ANCHOR'] / price_scaler, 2)}). Mandate: HARD WAIT.", metrics
            if risk_a < 0:
                # Within grace buffer -- treat as floor-exact entry (risk -> 0).
                risk_a = 0
            if risk_a == 0:
                # [PE-CAL-2] Price is exactly AT VWAP floor -- structurally optimal
                # pullback entry, but floor-based R:R is undefined (denominator = 0).
                # Substitute hard stop as risk denominator, same as floor-proximity.
                if reward_a <= 0:
                    return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: no upside reward from VWAP floor position.", metrics
                risk_a_hardstop = last['close'] - hard_stop_raw
                if risk_a_hardstop <= 0:
                    return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price at floor-exact entry.", metrics
                rr_hardstop = reward_a / risk_a_hardstop
                if rr_hardstop < 2.0:
                    metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                    metrics["Reward_Risk_Note"] = (
                        f"FLOOR_EXACT: price at VWAP; floor-based R:R undefined. "
                        f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails 1:2 minimum."
                    )
                    return "HALT", (
                        f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR EXACT): R:R {round(rr_hardstop, 2)}:1 < 2.0 "
                        f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                        f"Await wider reward ceiling or deeper pullback."
                    ), metrics
                metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                metrics["Reward_Risk_Note"] = (
                    f"FLOOR_EXACT: price at VWAP; R:R computed against hard stop "
                    f"({round(hard_stop_raw / price_scaler, 2)}). Displayed R:R reflects actual capital at risk."
                )
                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
            elif risk_a < (0.20 * atr_raw):
                # [PE-CAL-2] Risk denominator is near-zero (< 20% of ATR) -- the floor-based
                # R:R is degenerate (small price movements swing R:R by 10+ points).
                # Substitute the hard stop as the risk denominator. This gives the
                # Expectancy Gate a realistic number to enforce against.
                #
                # Rationale: The Expectancy Gate exists to prevent entries with poor
                # reward-to-risk. When price sits on the floor, floor-based risk approaches
                # zero and R:R approaches infinity -- the gate becomes meaningless.
                # The hard stop is what the operator actually risks if the trade reverses.
                # Using it as the denominator makes the gate enforceable.
                #
                # If hard-stop R:R < 2.0, HALT. The trade has valid structure (price at
                # floor) but insufficient upside relative to the real capital at risk.
                risk_a_hardstop = last['close'] - hard_stop_raw
                if risk_a_hardstop <= 0:
                    return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price in floor-proximity zone.", metrics
                rr_hardstop = reward_a / risk_a_hardstop
                if rr_hardstop < 2.0:
                    metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                    metrics["Reward_Risk_Note"] = (
                        f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                        f"substituted hard stop risk ({round(risk_a_hardstop / price_scaler, 2)}). "
                        f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails 1:2 minimum."
                    )
                    return "HALT", (
                        f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR PROXIMITY): R:R {round(rr_hardstop, 2)}:1 < 2.0 "
                        f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                        f"Floor-based R:R is degenerate (risk < 20% ATR). Await wider reward ceiling or deeper pullback."
                    ), metrics
                # Hard-stop R:R passes -- entry is valid with realistic R:R displayed.
                metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                metrics["Reward_Risk_Note"] = (
                    f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                    f"R:R computed against hard stop ({round(hard_stop_raw / price_scaler, 2)}). "
                    f"Displayed R:R reflects actual capital at risk, not floor distance."
                )
                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
            else:
                metrics["Reward_Risk"]      = round(reward_a / risk_a, 2)
                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)

        # [PE-7 PROFILE A GUARD] Ensure Profile A's Expectancy Gate doesn't overwrite
        # a scrubbed R:R if an EXIT signal is active (e.g. strict 3-bar VWAP counter).
        # The relocated PE-7 block fires before Pre-Check but also before the Expectancy
        # Gate. If Profile A passes Pre-Check but has EXIT from VWAP, the Expectancy Gate
        # would re-populate R:R -- this guard catches that edge case.
        if p_code == "A" and exit_signal == "EXIT":
            metrics["Reward_Risk"] = None
            metrics["Profit_Target"] = None

        # ======================================================================
        # PHASE 3: GATE EVALUATION  [MANDATE: DOC 2 SEC II, III, IV, VI, VII]
        # ======================================================================

        # Gate 1 -- Floor Integrity  [Doc 2 Sec 4.1]
        # Structural failure (threshold+ bars below) = immediate HALT.
        # VIOLATED (1-3 bars below) routes to Reclaim protocol -- checked in Phase 4.
        # A small grace buffer (-0.15 ATR) allows intrabar wicks below the floor.
        if pd.isna(atr_raw) or atr_raw == 0:
            return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid ATR for proximity math (ATR is NaN or 0).", metrics
        floor_dist = (last['close'] - last['ANCHOR']) / atr_raw
        if is_floor_failure:
            return "HALT", (f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break. (evaluated on last completed bar)" if p_code == "A" else f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break."), metrics
        if floor_dist < -0.15 and not is_violated:
            return "HALT", (f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor. (evaluated on last completed bar)" if p_code == "A" else f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor."), metrics

        # Gate 1.5 -- VIOLATED state with no current-bar reclaim
        # When is_violated=True but the current bar is still below the floor,
        # no downstream gate produces a meaningful output. Fire here immediately
        # rather than letting Phase 1.5 Expectancy or Phase 4 AMBIGUOUS catch it
        # with a misleading diagnostic.
        if is_violated and not is_reclaim:
            return (
                "HALT",
                f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: {consec_below} bar(s) below Floor ({floor_price}). "
                f"Current bar has NOT reclaimed (Close {round(last['close'] / price_scaler, 2)} < Floor {floor_price}). "
                f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}. "
                f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_below}/3 bars).",
                metrics
            )

        # Gate 3 -- Volume Climax  [Doc 2 Sec.II / Doc 6 Sec.3.6]
        climax_df = df.iloc[:-1] if p_code == "A" else df
        if pd.isna(climax_df['vol_sma_9'].iloc[-1]):
            return "HALT", "REJECT (reason: DATA INTEGRITY). Climax check failed: Volume SMA9 is NaN (insufficient volume history).", metrics
        climax, ago = check_climax_history(climax_df)
        if climax and ago is None:
            ago = 0
        if p_code == "A" and climax:
            ago += 1
        if climax:
            if is_reclaim:
                # Reclaim voided: cannot re-enter during the 3-bar climax window
                return "HALT", f"WAIT (reason: VOLUME CLIMAX). CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago.", metrics
            return "HALT", f"WAIT (reason: VOLUME CLIMAX). CLIMAX BLOCK: Institutional selling {ago} bars ago.", metrics

        # Gate 4 -- MID-RANGE Hard Wait  [Doc 2 Sec 4.2]
        # Must fire BEFORE Extension: extension is meaningless in a non-directional
        # regime. If ADX < 20, the asset has no trend to be extended from.
        #
        # [PE-11] Extension Warning: when MID-RANGE fires but extension would ALSO
        # fail, annotate the diagnostic so the operator knows two independent blocks
        # are active. Prevents wasted monitoring ("ADX just needs to cross 20...")
        # when the extension problem would immediately re-HALT the asset.
        _ext_warning = (
            f" [NOTE: Also EXTENDED at {atr_dist:.2f} ATR (limit {ext_limit}) "
            f"-- two independent blocks active]"
        ) if atr_dist > ext_limit else ""

        if adx_t < 20:
            return "HALT", f"WAIT (reason: MID-RANGE (ADX < 20)). MID-RANGE BLOCK: ADX ({adx_t:.2f}) < 20. HARD WAIT.{_ext_warning}", metrics
        if ma_squeeze:
            return "HALT", f"WAIT (reason: MID-RANGE (MA SQUEEZE)). MID-RANGE BLOCK: EMA 8/21 Squeeze 3+ bars. HARD WAIT.{_ext_warning}", metrics

        # ==================================================================
        # TIER 2 GATES: SIGNAL VALIDITY  [MANDATE: DOC 2 SEC V.2]
        # Doc 2 §V mandates Tier 2 (DI Preamble, Window, Modifiers) before
        # Tier 3 (Extension, Floor Proximity). These gates evaluate signal
        # quality before safety constraints filter on price distance.
        # ==================================================================

        # Gate 4.1 -- Directional Dominance  [Doc 2 Sec VI]
        # [R-6 FIX] Outer condition widened to universal scope. The previous
        # guard (p_code == "A" or is_etf or is_trending or is_resolving) silently
        # bypassed the DI check for Profile B/C in AMBIGUOUS state. Doc 2 §VI
        # defines the DI Preamble as universal ("Before evaluation, the system
        # must confirm +DI > -DI"). The practical impact was nil -- AMBIGUOUS
        # assets HALT at Phase 4 regardless -- but the diagnostic now correctly
        # shows DIRECTIONAL BLOCK instead of the downstream AMBIGUOUS label.
        if pd.isna(di_plus) or pd.isna(di_minus):
            return "HALT", "REJECT (reason: DATA INTEGRITY). Directional Dominance failed: DI values are NaN.", metrics
        if di_minus > di_plus:
            if p_code == "A" and ema_stacked:
                pass  # Profile A exemption: EMA 8 > EMA 21 stack intact
            elif p_code == "B" and _entry_trending and ma_stack_full:
                pass  # Profile B TRENDING exemption: full MA stack overrides momentary
                # -DI dominance during pullback corrective phase  [DOC 2 SEC VI]
            elif p_code == "C" and floor_prox_pct is not None and floor_prox_pct <= 5.0 and (adx_t > adx_t1):
                pass  # [PE-CAL-1 §6.6] Profile C counter-cyclical exemption:
                # within 5% of SMA 200 + positive ADX slope. WEALTH entries at the
                # structural floor are inherently counter-cyclical. -DI dominance is
                # expected during the decline that brings price to the floor.
            else:
                return "HALT", f"WAIT (reason: DIRECTIONAL BLOCK). DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f})", metrics

        # Gate 4.2 -- Modifier E Gap-Trap  [Doc 2 Sec VII]
        if (last['open'] > (prev_high + (0.5 * atr_raw))) and (last['close'] < last['open']):
            return "HALT", "REJECT (reason: GAP TRAP). MODIFIER E BLOCK: Gap-Trap. Immediate HALT.", metrics

        # Gate 4.3 -- Execution Window  [Doc 2 Sec III]
        # window_limit: A=4 hourly, B=5 daily, C=4 weekly [PE-CAL-1 §6.5]
        if window_count > window_limit:
            wc_label = "NONE FOUND (sentinel)" if window_count == 99 else str(window_count)
            return "HALT", f"WAIT (reason: WINDOW EXPIRED). WINDOW EXPIRED: Window {wc_label} (Requires 0-{window_limit}). PLANNING ONLY.", metrics

        # ==================================================================
        # TIER 3 GATES: SAFETY CONSTRAINTS  [MANDATE: DOC 2 SEC V.3]
        # Extension, Floor Proximity, and Expectancy audits. These fire after
        # signal validity is confirmed by Tier 2.
        # ==================================================================

        # Gate 5 -- Extension  [Doc 2 Sec VIII]
        # ext_limit is computed upstream (state and profile dependent).
        # Only evaluated once a directional regime (ADX > 20) is confirmed.
        #
        # [PE-CAL-1 FIX §6.2] Breakout Extension Exemption: For Profile B RESOLVING,
        # the 0.5 ATR limit confirms compression BEFORE the breakout. On the breakout
        # bar itself (close > 10-bar high), the limit self-contradicts -- a breakout is
        # by definition a move away from the anchor. Apply a 1.5 ATR runaway ceiling
        # instead: allows the breakout bar to extend through consolidation while still
        # blocking genuine chasing (price has run 1.5+ ATR past EMA 8).
        _is_breakout_bar = (last['close'] > resistance_raw) if p_code == "B" else False
        _effective_ext = 1.5 if (_is_breakout_bar and not is_trending and _entry_resolving) else ext_limit
        if atr_dist > _effective_ext and not (p_code == "B" and not is_etf and not (is_trending or is_resolving)):
            # Gate 5.5 -- Profile C Floor Proximity Audit  [Doc 2 Sec 4.3]
            # Wealth entries are only authorized when within range of the Weekly 200-SMA.
            # [PE-CAL-1 FIX §6.4] Threshold widened from 8% to 15%. The previous 8%
            # combined with 0.5 ATR EMA 21 extension created a dual-anchor impossibility.
            # Now both gates reference SMA 200: extension = 1.0 ATR from SMA 200,
            # floor proximity = 15% from SMA 200. Concentric circles, single anchor.
            if p_code == "C":
                if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
                    return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid SMA_200 for Floor Proximity Audit.", metrics
                if floor_prox_pct > 15.0:
                    return "HALT", f"REJECT (reason: FLOOR PROXIMITY FAILED). FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%.", metrics

            # ==================================================================
            # TREND QUALITY OVERRIDE ASSESSMENT  [MANDATE: DOC 2 SEC VIII.2]
            #
            # The extension gate HALT is maintained. This block evaluates whether
            # the Operator may exercise discretionary override under mandatory
            # risk-reduction constraints. The engine verdict remains HALT; the
            # override is an Operator-layer decision (Doc 4 §I).
            #
            # Eligibility (ALL must be true):
            #   1. Engine State = TRENDING (full MA stack, not RESOLVING)
            #   2. ADX_Accel = ACCELERATING (trend gaining momentum)
            #   3. Vol_Confirm = STRONG INSTITUTIONAL (ratio > 0.7)
            #   4. Extension <= profile ceiling (B: 2.0 ATR, C: 1.0 ATR)
            #   5. Exit_Signal = false
            #   6. Resistance exists (not suppressed) AND Override R:R >= 0.5 [PE-13 revised]
            #
            # Ineligible: Profile A (hourly -- no weeks-long opportunity cost),
            #             ETF (TRENDING suppressed by Logic Lock -- condition 1
            #             structurally impossible).
            #
            # Override terms (non-negotiable):
            #   - 50% unit sizing
            #   - Tightened stop: Floor - 1.0 ATR (vs standard 1.5 ATR)
            #   - Resistance (10-bar high) is mandatory exit (no open-ended runner)
            # ==================================================================

            _override_ceiling = {
                "B": 2.0,    # 1.0 ATR override window above 1.0 base
                "C": 2.0,    # 1.0 ATR override window above 1.0 base [PE-CAL-1 §6.4: realigned from 1.0]
            }
            _ceil = _override_ceiling.get(p_code)

            if _ceil is not None and not is_etf:
                _ov_trending     = is_trending
                _ov_accel        = adx_accel_state == "ACCELERATING"
                _ov_vol          = vol_confirm_state == "STRONG INSTITUTIONAL"
                _ov_within_ceil  = atr_dist <= _ceil
                _ov_no_exit      = (exit_signal == False)  # [PE-28] Any active signal (WARNING or EXIT) blocks override

                _tight_stop_raw  = structural_floor_raw - (1.0 * atr_raw)
                _tight_stop      = round(_tight_stop_raw / price_scaler, 2)

                # [PE-13 REVISED] Override target = Resistance (10-bar consolidation high).
                # The original Floor + 1.5 ATR formula is structurally incompatible with
                # extended entries: in any established TRENDING state, the EMA_21-SMA_50 gap
                # exceeds 0.5 ATR, making Floor + 1.5 ATR < Price a mathematical certainty.
                #
                # Resistance is the correct target because:
                #   (a) It's a real structural level (10-bar high), not a synthetic computation
                #   (b) If price is already above it (suppressed), no forward target exists
                #       and the override is naturally ineligible
                #   (c) The R:R against the tightened stop enforces positive expectancy
                #
                # Condition 6: Resistance must exist (not suppressed) AND override R:R >= 0.5.
                # The 0.5 minimum (1:2 risk-adjusted) reflects the inferior entry quality:
                # a standard entry near the floor demands 1:1 or better; an override entry
                # at an extended price accepts lower reward per unit risk but must still show
                # meaningful positive expectancy.
                _ov_has_target   = not _resistance_suppressed
                if _ov_has_target:
                    _ov_target   = resistance_display
                    _ov_reward   = resistance_raw - last['close']
                    _ov_risk     = last['close'] - _tight_stop_raw
                    _ov_rr       = round(_ov_reward / _ov_risk, 2) if _ov_risk > 0 else 0
                    _ov_rr_pass  = _ov_rr >= 0.5
                else:
                    _ov_target   = None
                    _ov_rr       = None
                    _ov_rr_pass  = False

                _ov_eligible     = all([_ov_trending, _ov_accel, _ov_vol,
                                        _ov_within_ceil, _ov_no_exit,
                                        _ov_has_target, _ov_rr_pass])

                if _ov_eligible:
                    metrics["Trend_Quality_Override"] = {
                        "Eligible": True,
                        "Conditions_Met": (
                            f"TRENDING + ACCELERATING (ADX_Accel {adx_accel}) + "
                            f"STRONG_VOL ({vol_confirm_ratio}) + "
                            f"Extension {atr_dist:.2f} <= {_ceil} ceiling + "
                            f"Override R:R {_ov_rr} >= 0.5 (Target {_ov_target})"
                        ),
                        "Override_Terms": (
                            f"50% unit | Stop: {_tight_stop} (Floor - 1.0 ATR) | "
                            f"Target: {_ov_target} (Resistance -- mandatory exit)"
                        ),
                        "Tight_Stop": _tight_stop,
                        "Override_Target": _ov_target,
                        "Override_RR": _ov_rr,
                        "Note": (
                            "OPERATOR DISCRETION: All 6 conditions met. Override permitted "
                            "under reduced sizing and tightened risk. This is NOT a standard PASS."
                        )
                    }
                else:
                    # Build rejection reason(s)
                    _ov_fails = []
                    if not _ov_trending:    _ov_fails.append("Engine State not TRENDING (MA stack incomplete)")
                    if not _ov_accel:       _ov_fails.append(f"ADX not ACCELERATING ({adx_accel_state})")
                    if not _ov_vol:         _ov_fails.append(f"Volume not STRONG INSTITUTIONAL ({vol_confirm_state})")
                    if not _ov_within_ceil: _ov_fails.append(f"Extension {atr_dist:.2f} exceeds {_ceil} ATR ceiling")
                    if not _ov_no_exit:     _ov_fails.append("Exit_Signal active")
                    if not _ov_has_target:  _ov_fails.append(
                        "Resistance suppressed (price above 10-bar high) -- no forward target"
                    )
                    if _ov_has_target and not _ov_rr_pass: _ov_fails.append(
                        f"Override R:R {_ov_rr} < 0.5 minimum (Target {_ov_target}, "
                        f"Stop {_tight_stop}) -- insufficient reward for extended entry"
                    )
                    metrics["Trend_Quality_Override"] = {
                        "Eligible": False,
                        "Reason": "; ".join(_ov_fails),
                        "Note": "Extension rejection is protective. Do not chase."
                    }
            else:
                # Profile A or ETF: override structurally ineligible
                _inelig_reason = (
                    "Profile A (hourly timeframe -- no prolonged opportunity cost)"
                    if p_code == "A" else
                    "ETF (TRENDING state suppressed by Logic Lock)"
                    if is_etf else
                    "Unknown profile"
                )
                metrics["Trend_Quality_Override"] = {
                    "Eligible": False,
                    "Reason": f"Override ineligible: {_inelig_reason}",
                    "Note": "Extension rejection is protective. Do not chase."
                }

            return "HALT", f"WAIT (reason: EXTENDED). EXTENDED: {atr_dist:.2f} ATR above limit ({_effective_ext})", metrics

        # Gate 5.5 -- Profile C Floor Proximity Audit  [Doc 2 Sec 4.3]
        # [PE-CAL-1 FIX §6.4] Threshold widened from 8% to 15% (see Gate 5.5 inside extension).
        if p_code == "C":
            if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
                return "HALT", "REJECT (reason: DATA INTEGRITY). Invalid SMA_200 for Floor Proximity Audit.", metrics
            if floor_prox_pct > 15.0:
                return "HALT", f"REJECT (reason: FLOOR PROXIMITY FAILED). FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%.", metrics


        # Gate 5.6 -- Profile A Expectancy Gate  [Doc 2 Sec 4.3 / P032 / P038]
        # Enforced here so it applies to ALL PASS paths: Pullback, Breakout, Reclaim.
        # No Profile A trade may bypass the 1:2 reward/risk requirement.
        # Note: risk_a < 0 is unreachable here -- clamped to 0 by grace buffer (line ~1734)
        # or returned HALT for material breach (line ~1731) in the upstream Expectancy Gate.
        if p_code == "A":
            if risk_a == 0:
                pass  # Floor-exact entry: R:R already validated by PE-CAL-2. Gate passes.
            elif reward_a < (2.0 * risk_a):
                if reward_a <= 0:
                    reason = (
                        f"Price {round(last['close'] / price_scaler, 2)} has already exceeded "
                        f"Consolidation High {cons_high_raw / price_scaler:.2f} -- no reward remaining. "
                        f"Mandate: WAIT for pullback to VWAP ({floor_price}) before re-evaluating."
                    )
                else:
                    reason = (
                        f"Reward {reward_a / price_scaler:.2f} < 2x Risk {risk_a / price_scaler:.2f}. "
                        f"Consolidation High {cons_high_raw / price_scaler:.2f} too close to entry. "
                        f"Mandate: WAIT for pullback to VWAP ({floor_price})."
                    )
                return "HALT", f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY GATE FAILED (Profile A): {reason}", metrics

        # ======================================================================
        # CEG-001: CAPITAL EXPECTANCY GATE  [Spec Section 2.1]
        # Evaluates reward-to-risk using actual capital at risk (Price − Hard_Stop)
        # rather than floor distance. SSG-001 has already adjusted hard_stop_raw
        # if needed, so capital_risk reflects the corrected stop.
        #
        # Profile A: mandatory gate. HALT if capital_rr < 1.0.
        # Profile B: compute for transparency, do NOT gate.
        # Profile C: not applicable (no profit targets).
        #
        # Mutual exclusivity: PE-CAL-2 fires when risk_a < 20% ATR.
        # CEG-001 fires when risk_a >= 20% ATR. No overlap.
        # ======================================================================
        _capital_rr = None
        _reward_label = None

        if p_code == "A" and risk_a >= (0.20 * atr_raw):
            _capital_reward = cons_high_raw - last['close']
            _capital_risk   = last['close'] - hard_stop_raw
            if _capital_risk > 0 and _capital_reward > 0:
                _capital_rr = _capital_reward / _capital_risk
                metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
                if _capital_rr < 1.0:
                    return "HALT", (
                        f"REJECT (reason: CAPITAL EXPECTANCY FAILED). CAPITAL EXPECTANCY FAILED: Capital R:R {round(_capital_rr, 2)} "
                        f"-- reward ${round(_capital_reward / price_scaler, 2)} vs. "
                        f"stop risk ${round(_capital_risk / price_scaler, 2)}. Minimum: 1.0."
                    ), metrics
                elif _capital_rr < 1.5:
                    _reward_label = "NARROW"
                else:
                    _reward_label = "HEALTHY"
                metrics["Capital_RR_Label"] = _reward_label
            elif _capital_risk > 0:
                # Reward <= 0: no upside remaining (already handled by Gate 5.6 in most
                # cases, but write metric for completeness)
                _capital_rr = 0.0
                metrics["Capital_Reward_Risk"] = 0.0
                metrics["Capital_RR_Label"] = None
            else:
                # capital_risk <= 0: stop above price (floor broken state)
                metrics["Capital_Reward_Risk"] = None
                metrics["Capital_RR_Label"] = None
        elif p_code == "A":
            # PE-CAL-2 handled this case (risk_a < 20% ATR).
            # Capital R:R is still computable for dashboard visibility.
            _capital_reward = cons_high_raw - last['close']
            _capital_risk   = last['close'] - hard_stop_raw
            if _capital_risk > 0 and _capital_reward > 0:
                _capital_rr = _capital_reward / _capital_risk
                metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
                if _capital_rr < 1.5:
                    _reward_label = "NARROW"
                else:
                    _reward_label = "HEALTHY"
                metrics["Capital_RR_Label"] = _reward_label
            else:
                metrics["Capital_Reward_Risk"] = None
                metrics["Capital_RR_Label"] = None
        elif p_code == "B":
            # Profile B: compute Capital_Reward_Risk for transparency, no gate.
            _capital_reward_b = resistance_raw - last['close']
            _capital_risk_b   = last['close'] - hard_stop_raw
            if _capital_risk_b > 0 and _capital_reward_b > 0:
                _capital_rr_b = _capital_reward_b / _capital_risk_b
                metrics["Capital_Reward_Risk"] = round(_capital_rr_b, 2)
                _capital_rr = _capital_rr_b  # for diagnostic label
                if _capital_rr_b < 1.5:
                    _reward_label = "NARROW"
                else:
                    _reward_label = "HEALTHY"
            else:
                metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None  # Not written for Profile B per spec
        else:
            # Profile C: not applicable
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None

        # ======================================================================
        # PHASE 4: TRIGGER IDENTIFICATION & CADENCE BINDING
        # [MANDATE: DOC 2 SEC VI]
        #
        # Priority order (most restrictive first):
        #   1. VIOLATED state + current bar reclaim -> Reclaim Protocol
        #   2. TRENDING state                       -> Standard/Pullback Protocol
        #   3. RESOLVING state                      -> Convexity/Breakout Protocol
        #   4. ADX 20-25 without MA stack           -> AMBIGUOUS HALT
        #
        # Current-bar positional checks are evaluated independently from the
        # historical Is_Pullback / Is_Breakout columns used for window counting.
        # ======================================================================

        # Current-bar position flags (independent of window-reset columns)
        # [PE-CAL-1 FIX §6.1] Profile B pullback zone upper bound: EMA 21 + 0.5 ATR.
        # Floor (ANCHOR = SMA 50) remains the lower bound. The zone now encompasses
        # the natural pullback channel between SMA 50 and EMA 21.
        _pb_upper_cur = (last['EMA_21'] + (0.5 * atr_raw)) if p_code == "B" else (last['ANCHOR'] + (0.5 * atr_raw))
        at_pullback_zone = (
                (last['close'] >= last['ANCHOR']) and
                (last['close'] <= _pb_upper_cur)
        )

        # [MANDATE: DOC 2 SEC VI.2] Convex Support: Price > EMA 8 required at breakout.
        # [PE-BUG-1 FIX] ETF Exemption: Convexity Protocol is bypassed (Doc 6 §3.4.1).
        # ETF breakout validates against baseline floor (ANCHOR) instead of EMA 8.
        # resistance_raw pre-computed before Phase 1.5 -- no re-definition needed here.
        _convex_support_level = last['ANCHOR'] if is_etf else last['EMA_8']
        at_breakout = (
                (last['close'] > resistance_raw) and
                (last['close'] > _convex_support_level)
        )

        # ---- PHASE 4: SINGLE if/elif/elif/else CHAIN ----
        # All four paths are mutually exclusive. The first matching condition
        # sets verdict/diag and falls through to Phase 4B (Focus chart).
        # Only HALT paths use inline return. PASS paths never inline-return.
        #
        # Priority order:
        #   1. RECLAIM   -- VIOLATED state + current bar above floor
        #   2. TRENDING  -- ADX > 25 + full MA stack  (pullback protocol)
        #   3. RESOLVING -- ADX > 20 + 3-bar slope    (breakout protocol)
        #   4. AMBIGUOUS -- ADX 20-25, no confirmed state
        #
        # [PE-BUG-1 FIX] Branches use _entry_trending / _entry_resolving composites.
        # For non-ETF these equal is_trending / is_resolving (identity).
        # For ETF these use the pre-Logic-Lock snapshot, allowing ETFs to reach
        # PASS paths while is_trending/is_resolving remain False for floor policy.

        # ---- PRIORITY 1: RECLAIM PROTOCOL  [Doc 2 Sec VI.3] ----
        if is_reclaim:
            # State quality gate: reclaim is only a valid re-entry signal if the
            # underlying directional state is confirmed (TRENDING or RESOLVING).
            # An AMBIGUOUS reclaim means price has recovered the floor but the trend
            # regime is not active -- this is a structural bounce, not a qualified entry.
            if not (_entry_trending or _entry_resolving):
                return (
                    "HALT",
                    f"WAIT (reason: RECLAIM WITHOUT REGIME). RECLAIM DETECTED but state AMBIGUOUS: ADX {adx_t:.1f} -- MA stack incomplete "
                    f"and no confirmed 3-bar ADX slope. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                    f"but directional regime not active. Mandate: HARD WAIT. "
                    f"Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.",
                    metrics
                )
            verdict = "PASS"
            _reclaim_state = "TRENDING" if _entry_trending else "RESOLVING"
            _reclaim_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            diag    = (
                f"PRE-APPROVED (entry: RECLAIM | state: {_reclaim_state} | "
                f"reward: {_reclaim_reward} | trigger: BAR CLOSE ONLY). "
                f"Current bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                f"after {consec_below} prior bar(s) below Floor. "
                f"ADX: {adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close above {floor_price} before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )

        # ---- PRIORITY 2: TRENDING STATE -- Standard/Pullback Protocol  [Doc 2 Sec VI.1] ----
        elif _entry_trending:
            if at_pullback_zone:
                verdict = "PASS"
                _pb_reward = (
                    f"{_reward_label} [{_capital_rr:.2f}]"
                    if _reward_label and _capital_rr is not None
                    else "N/A"
                )
                diag    = (
                    f"PRE-APPROVED (entry: PULLBACK | state: TRENDING | "
                    f"reward: {_pb_reward} | trigger: BAR CLOSE ONLY). "
                    f"Price {round(last['close'] / price_scaler, 2)} within pullback zone "
                    f"[{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}]. "
                    f"ADX: {adx_t:.1f}. "
                    f"Entry: execute at THIS bar's close. "
                    f"If close missed: next bar must ALSO close within pullback zone before entry is valid. "
                    f"Stop: {hard_stop}. {chart_ref}"
                )
            else:
                return (
                    "HALT",
                    f"WAIT (reason: NOT IN PULLBACK ZONE). TRENDING (ADX {adx_t:.1f}) -- price not in pullback zone. "
                    f"Mandate: WAIT for Floor Test at {floor_price}.",
                    metrics
                )

        # ---- PRIORITY 3: RESOLVING STATE -- Convexity/Breakout Protocol  [Doc 2 Sec VI.2] ----
        # [MANDATE: DOC 2 SEC VI] Profile A Exemption: "The Convexity Protocol is architecturally
        # incompatible with mean-reversion entries." Profile A is a VWAP pullback profile only.
        # A RESOLVING Profile A asset must wait for price to return to the VWAP floor.
        elif _entry_resolving:
            if p_code == "A":
                return (
                    "HALT",
                    f"WAIT (reason: PROFILE A RESOLVING BLOCK). CONVEXITY PROTOCOL BLOCKED (Profile A): "
                    f"Profile A is a mean-reversion profile -- VWAP pullback entry only. "
                    f"Mandate: WAIT for price to return to VWAP floor ({floor_price}). "
                    f"ADX: {adx_t:.1f} (RESOLVING state active).",
                    metrics
                )
            if at_breakout:
                verdict = "PASS"
                sizing  = "Full Unit" if conviction_state.startswith("HIGH") else "50% Unit (Low Conviction)"
                _bo_reward = (
                    f"{_reward_label} [{_capital_rr:.2f}]"
                    if _reward_label and _capital_rr is not None
                    else "N/A"
                )
                diag    = (
                    f"PRE-APPROVED (entry: BREAKOUT | state: RESOLVING | "
                    f"reward: {_bo_reward} | trigger: INTRADAY). "
                    f"Price {round(last['close'] / price_scaler, 2)} closed above resistance "
                    f"{round(resistance_raw / price_scaler, 2)}. "
                    f"ADX: {adx_t:.1f}. Sizing: {sizing}. "
                    f"Entry: INTRADAY permitted -- may enter while breakout bar is still forming. "
                    f"{'Floor Support' if is_etf else 'Convex Support'}: price must remain above "
                    f"{'baseline floor' if is_etf else 'EMA 8'} ({round(_convex_support_level / price_scaler, 2)}). "
                    f"Stop: {hard_stop}. {chart_ref}"
                )
            else:
                reason = (
                    "No breakout above resistance"  if not df['Is_Breakout'].iloc[-1]
                    else ("Floor Support failed: Price below baseline floor" if is_etf
                          else "Convex Support failed: Price below EMA 8")
                )
                return (
                    "HALT",
                    f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {adx_t:.1f}) -- {reason} at "
                    f"{round(resistance_raw / price_scaler, 2)}. "
                    f"Mandate: WAIT for Consolidation Range violation.",
                    metrics
                )

        # ---- PRIORITY 4: AMBIGUOUS (ADX 20-25, MA stack incomplete) ----
        else:
            return (
                "HALT",
                f"WAIT (reason: AMBIGUOUS STATE). ENGINE STATE AMBIGUOUS: ADX {adx_t:.1f} > 20 but TRENDING not confirmed "
                f"(MA stack incomplete or ADX < 25). Mandate: HARD WAIT.",
                metrics
            )

        # ==================================================================
        # PE-30: Align Resistance_Note with BREAKOUT verdict
        # When resistance is suppressed AND entry = BREAKOUT, the "await
        # pullback" note (written pre-Phase 4) contradicts the entry thesis.
        # Resistance is now the broken level, not a forward target.
        # Overwrite with breakout-aligned context.
        # ==================================================================
        if verdict == "PASS" and _resistance_suppressed and at_breakout:
            metrics["Resistance_Note"] = (
                f"BROKEN: resistance ({resistance_display}) violated on breakout. "
                f"Now support reference. "
                f"{'Convex' if not is_etf else 'Floor'} Support: "
                f"{'EMA 8' if not is_etf else 'baseline floor'} "
                f"({round(_convex_support_level / price_scaler, 2)})."
            )

        # ======================================================================
        # PHASE 4B: FOCUS CHART -- generated ONLY after a confirmed PASS
        # [MANDATE: DOC 4 SEC VII]
        # A Focus chart failure must NOT block a valid PASS verdict.
        # ======================================================================

        focus_path = os.path.join(chart_dir, f"{clean_ticker}_focus.png")
        try:
            _build_focus_chart(
                df, p_code, profile, clean_ticker, price_scaler,
                adx_col, dmp_col, dmn_col
            ).write_image(focus_path)
            diag += f" | Focus: {focus_path}"
        except Exception as focus_err:
            diag += f" | [Focus chart skipped: {str(focus_err)}]"

        # ======================================================================
        # ENG-002: FIBONACCI RETRACEMENT CONFLUENCE DIAGNOSTIC  [Amendment ENG-002]
        # Scope: Profile B (TREND), TRENDING state only. Not computed for
        # Profile A, Profile C, RESOLVING state, or ETFs.
        # Rally leg: Origin = 10-bar Focus Window Lowest Low;
        #            Peak   = 10-bar Focus Window Highest High (= resistance_raw).
        # Confluence tolerance: ±0.3% of the Fibonacci level.
        # NON-GATE: informational only. No verdict or gate impact.
        # ======================================================================
        if p_code == "B" and _entry_trending and not is_etf:
            _fib_window  = df.iloc[-11:-1]
            _fib_origin  = float(_fib_window['low'].min())
            _fib_peak    = float(_fib_window['high'].max())
            _fib_range   = _fib_peak - _fib_origin

            if _fib_range > 0:
                _fib_382_raw = _fib_peak - 0.382 * _fib_range
                _fib_500_raw = _fib_peak - 0.500 * _fib_range

                # Scale to display currency (pence → pounds for GBP)
                metrics["Fib_382_Level"] = round(_fib_382_raw / price_scaler, 2)
                metrics["Fib_500_Level"] = round(_fib_500_raw / price_scaler, 2)

                _current_price = last['close']
                _tol_382 = 0.003 * _fib_382_raw
                _tol_500 = 0.003 * _fib_500_raw

                if abs(_current_price - _fib_382_raw) <= _tol_382:
                    metrics["Fib_Confluence"] = "CONFLUENCE_382"
                elif abs(_current_price - _fib_500_raw) <= _tol_500:
                    metrics["Fib_Confluence"] = "CONFLUENCE_500"
                elif _fib_500_raw <= _current_price <= _fib_382_raw:
                    metrics["Fib_Confluence"] = "BETWEEN_FIBS"
                elif _current_price > _fib_382_raw:
                    metrics["Fib_Confluence"] = "ABOVE_FIBS"
                else:
                    metrics["Fib_Confluence"] = "BELOW_FIBS"
            else:
                # Degenerate range (Origin == Peak) -- cannot compute Fibonacci levels
                metrics["Fib_382_Level"]  = None
                metrics["Fib_500_Level"]  = None
                metrics["Fib_Confluence"] = None
        else:
            metrics["Fib_382_Level"]  = None
            metrics["Fib_500_Level"]  = None
            metrics["Fib_Confluence"] = None

        return verdict, diag, metrics

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", {}
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",     required=True)
    parser.add_argument("--profile",    default="TREND")
    parser.add_argument("--mode",       default="INFO")
    parser.add_argument("--etf",        action="store_true")
    parser.add_argument("--convexity",  default=None, choices=["C1", "C2", "C3"],
                        help="Convexity classification (from Classification Prompt). "
                             "Omit for unclassified assets (defaults to C-1 behaviour).")
    args = parser.parse_args()

    # --- PE-5: PROFILE INPUT VALIDATION (Bug #PE-5) ---
    # Prevents silent misclassification when an invalid profile string is passed.
    # Without this gate, unrecognised profiles fall through to TREND via the
    # p_mapping default, producing a silent wrong-profile evaluation.
    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if args.profile.upper() not in VALID_PROFILES:
        print(json.dumps({
            "status": "ERROR",
            "diagnostic": f"INVALID PROFILE: '{args.profile}' is not recognised. "
                          f"Valid profiles: SWING (A), TREND (B), WEALTH (C).",
            "metrics": {}
        }, indent=4))
        import sys
        sys.exit(1)

    status, diag, metrics = run_tbs_engine(
        args.ticker, args.profile, args.etf, args.mode,
        convexity_class=args.convexity
    )
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))

import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
# TBS PURITY ENGINE (Layer 2) v8.6
# CONVEXITY INTEGRATION: Option B (Minimum Viable C-3)
# EPX-001: Entry Proximity Signal (post-verdict diagnostic audit)
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
# EPX-001:   Entry Proximity Signal. Post-verdict diagnostic audit surfaces APPROACHING
#            when exactly one single-bar-proximity gate blocks HALT and all structural
#            gates pass. Five new metrics: Proximity_Signal, Proximity_Blocking_Gate,
#            Proximity_Distance, Proximity_Target, Proximity_Note. Purely informational —
#            no verdict, gate, threshold, stop, target, or sizing changes.
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


def _clamp(v, lo, hi):
    """Clamp value v to the range [lo, hi]. Promoted to module level in Phase 6."""
    return max(lo, min(hi, v))


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
# PHASE 1 — EXTRACTED GATE FUNCTIONS  [RFT-001]
#
# Each gate returns None if passed, or (status: str, diagnostic: str) if failed.
# Gate order matches Engine Execution Map v1.9 §II.
# These are structural extractions — zero logic changes from inline originals.
# ==============================================================================


def _gate_context_regime(p_code, df_ctx, price_scaler, metrics):
    """CRG-1 (Profile A) + CRG-2 (Profile B) — Context Regime Gate [Doc 2 Amendment].
    Returns None if passed, or (status, diagnostic) if failed."""

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
                return ("HALT", (
                    f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED (Profile A): {' + '.join(_crg_failures)}. "
                    f"Hourly execution requires daily structural uptrend. "
                    f"Mandate: asset disqualified until daily regime recovers."
                ))
        else:
            # df_ctx unavailable or SMA columns NaN -- cannot verify regime
            metrics["Context_Golden_Cross"]    = None
            metrics["Context_Price_vs_SMA200"] = None
            metrics["Context_SMA200"]          = None
            return ("HALT", (
                "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: Insufficient daily data for SMA 200 computation. "
                "Cannot verify structural regime."
            ))

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
                return ("HALT", (
                    "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                    "Insufficient weekly data for SMA 50 slope computation. "
                    "Cannot verify structural regime."
                ))

            weekly_sma50_rising = bool(current_weekly_sma50 > prior_weekly_sma50)
            slope_value = round((current_weekly_sma50 - prior_weekly_sma50) / price_scaler, 2)

            metrics["Context_Weekly_SMA50_Slope"]  = slope_value
            metrics["Context_Weekly_SMA50_Rising"] = weekly_sma50_rising
            metrics["Context_Weekly_SMA50"]        = round(current_weekly_sma50 / price_scaler, 2)

            if not weekly_sma50_rising:
                return ("HALT", (
                    f"REJECT (reason: CONTEXT REGIME FAILED). CONTEXT REGIME FAILED "
                    f"(Profile B): Weekly SMA 50 declining (slope: {slope_value}). "
                    f"Intermediate-term trend not confirmed. Daily execution requires "
                    f"weekly structural improvement. Mandate: asset disqualified until "
                    f"weekly SMA 50 turns positive."
                ))
        else:
            # df_ctx unavailable or < 2 bars or SMA_50 column missing
            metrics["Context_Weekly_SMA50_Slope"]  = None
            metrics["Context_Weekly_SMA50_Rising"] = None
            metrics["Context_Weekly_SMA50"]        = None
            return ("HALT", (
                "REJECT (reason: DATA INTEGRITY). CONTEXT REGIME: "
                "Insufficient weekly data for SMA 50 computation. "
                "Cannot verify structural regime."
            ))

    return None  # Gate passed


def _gate_liquidity(adv_20, is_etf, _is_lse_etf, metrics):
    """Gate 0 — Liquidity Check [Doc 2 Sec.II / Doc 8 Sec.II-IV].
    Returns None if passed, or (status, diagnostic) if failed."""

    _adv_limit_early = 5_000_000 if _is_lse_etf else (50_000_000 if is_etf else 5_000_000)
    if not pd.isna(adv_20) and adv_20 < _adv_limit_early:
        return ("HALT", f"REJECT (reason: LIQUIDITY FAILED). Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${_adv_limit_early/1e6:.0f}M)")
    return None  # Gate passed


def _gate_data_integrity(atr_raw, metrics):
    """Data Integrity Check (ATR NaN/0) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""

    if pd.isna(atr_raw) or atr_raw == 0:
        return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid ATR for proximity math (ATR is NaN or 0).")
    return None  # Gate passed


def _gate_floor_failure(consec_below, is_floor_failure, p_code, metrics):
    """Gate 1 — Floor Failure [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    if is_floor_failure:
        return ("HALT", (f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break. (evaluated on last completed bar)" if p_code == "A" else f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break."))
    return None  # Gate passed


def _gate_floor_violation(floor_dist, is_violated, p_code, metrics):
    """Gate 1 — Floor Violation (floor_dist check) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    if floor_dist < -0.15 and not is_violated:
        return ("HALT", (f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor. (evaluated on last completed bar)" if p_code == "A" else f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor."))
    return None  # Gate passed


def _gate_floor_violation_active(is_violated, is_reclaim, consec_below, floor_price,
                                 last_close, price_scaler, metrics):
    """Gate 1.5 — Floor Violation Active (no reclaim) [Doc 2 Sec 4.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    if is_violated and not is_reclaim:
        return (
            "HALT",
            f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: {consec_below} bar(s) below Floor ({floor_price}). "
            f"Current bar has NOT reclaimed (Close {round(last_close / price_scaler, 2)} < Floor {floor_price}). "
            f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}. "
            f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_below}/3 bars)."
        )
    return None  # Gate passed


def _gate_climax(df, p_code, is_reclaim, check_climax_history_fn, metrics):
    """Gate 3 — Volume Climax [Doc 2 Sec.II / Doc 6 Sec.3.6].
    Returns None if passed, or (status, diagnostic) if failed."""

    climax_df = df.iloc[:-1] if p_code == "A" else df
    if pd.isna(climax_df['vol_sma_9'].iloc[-1]):
        return ("HALT", "REJECT (reason: DATA INTEGRITY). Climax check failed: Volume SMA9 is NaN (insufficient volume history).")
    climax, ago = check_climax_history_fn(climax_df)
    if climax and ago is None:
        ago = 0
    if p_code == "A" and climax:
        ago += 1
    if climax:
        if is_reclaim:
            # Reclaim voided: cannot re-enter during the 3-bar climax window
            return ("HALT", f"WAIT (reason: VOLUME CLIMAX). CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago.")
        return ("HALT", f"WAIT (reason: VOLUME CLIMAX). CLIMAX BLOCK: Institutional selling {ago} bars ago.")
    return None  # Gate passed


def _gate_midrange(adx_t, ma_squeeze, atr_dist, ext_limit, metrics):
    """Gate 4 — MID-RANGE Hard Wait [Doc 2 Sec 4.2].
    Returns None if passed, or (status, diagnostic) if failed."""
    # [PE-11] Extension Warning: when MID-RANGE fires but extension would ALSO
    # fail, annotate the diagnostic so the operator knows two independent blocks
    # are active.
    _ext_warning = (
        f" [NOTE: Also EXTENDED at {atr_dist:.2f} ATR (limit {ext_limit}) "
        f"-- two independent blocks active]"
    ) if atr_dist > ext_limit else ""

    if adx_t < 20:
        return ("HALT", f"WAIT (reason: MID-RANGE (ADX < 20)). MID-RANGE BLOCK: ADX ({adx_t:.2f}) < 20. HARD WAIT.{_ext_warning}")
    if ma_squeeze:
        return ("HALT", f"WAIT (reason: MID-RANGE (MA SQUEEZE)). MID-RANGE BLOCK: EMA 8/21 Squeeze 3+ bars. HARD WAIT.{_ext_warning}")
    return None  # Gate passed


def _gate_directional(di_plus, di_minus, p_code, ema_stacked, _entry_trending,
                      ma_stack_full, floor_prox_pct, adx_t, adx_t1, metrics):
    """Gate 4.1 — Directional Dominance [Doc 2 Sec VI].
    Returns None if passed, or (status, diagnostic) if failed."""

    if pd.isna(di_plus) or pd.isna(di_minus):
        return ("HALT", "REJECT (reason: DATA INTEGRITY). Directional Dominance failed: DI values are NaN.")
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
            return ("HALT", f"WAIT (reason: DIRECTIONAL BLOCK). DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f})")
    return None  # Gate passed


def _gate_modifier_e(last_open, prev_high, atr_raw, last_close, metrics):
    """Gate 4.2 — Modifier E Gap-Trap [Doc 2 Sec VII].
    Returns None if passed, or (status, diagnostic) if failed."""
    if (last_open > (prev_high + (0.5 * atr_raw))) and (last_close < last_open):
        return ("HALT", "REJECT (reason: GAP TRAP). MODIFIER E BLOCK: Gap-Trap. Immediate HALT.")
    return None  # Gate passed


def _gate_window(window_count, window_limit, metrics):
    """Gate 4.3 — Execution Window [Doc 2 Sec III].
    Returns None if passed, or (status, diagnostic) if failed."""
    if window_count > window_limit:
        wc_label = "NONE FOUND (sentinel)" if window_count == 99 else str(window_count)
        return ("HALT", f"WAIT (reason: WINDOW EXPIRED). WINDOW EXPIRED: Window {wc_label} (Requires 0-{window_limit}). PLANNING ONLY.")
    return None  # Gate passed


def _gate_extension(atr_dist, ext_limit, p_code, is_etf, is_trending, is_resolving,
                    _entry_trending, _entry_resolving, last, resistance_raw,
                    resistance_display, _resistance_suppressed, floor_prox_pct,
                    adx_accel_state, adx_accel, vol_confirm_state, vol_confirm_ratio,
                    exit_signal, structural_floor_raw, atr_raw, price_scaler,
                    metrics):
    """Gate 5 — Extension [Doc 2 Sec VIII].
    Returns None if passed, or (status, diagnostic) if failed."""

    # [PE-CAL-1 FIX §6.2] Breakout Extension Exemption
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
                return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid SMA_200 for Floor Proximity Audit.")
            if floor_prox_pct > 15.0:
                return ("HALT", f"REJECT (reason: FLOOR PROXIMITY FAILED). FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%.")

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
        #   5. No Exit_Signal active  [PE-28]
        #   6. Resistance not suppressed + Override R:R >= 0.5  [PE-13 REVISED]
        #
        # Override is structurally ineligible for:
        #   - Profile A (hourly timeframe -- override would only save ~1 bar)
        #   - ETF (TRENDING suppressed by Logic Lock -- condition 1
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

        return ("HALT", f"WAIT (reason: EXTENDED). EXTENDED: {atr_dist:.2f} ATR above limit ({_effective_ext})")

    return None  # Gate passed


def _gate_floor_proximity_c(p_code, last, floor_prox_pct, metrics):
    """Gate 5.5 — Profile C Floor Proximity Audit [Doc 2 Sec 4.3].
    Returns None if passed, or (status, diagnostic) if failed."""

    if p_code == "C":
        if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
            return ("HALT", "REJECT (reason: DATA INTEGRITY). Invalid SMA_200 for Floor Proximity Audit.")
        if floor_prox_pct > 15.0:
            return ("HALT", f"REJECT (reason: FLOOR PROXIMITY FAILED). FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 15.0%.")
    return None  # Gate passed


def _gate_expectancy(p_code, risk_a, reward_a, cons_high_raw, last_close,
                     floor_price, price_scaler, metrics):
    """Gate 5.6 — Expectancy Gate (Profile A) [Doc 2 Sec 4.3 / P032 / P038].
    Returns None if passed, or (status, diagnostic) if failed."""
    if p_code == "A":
        if risk_a == 0:
            pass  # Floor-exact entry: R:R already validated by PE-CAL-2. Gate passes.
        elif reward_a < (2.0 * risk_a):
            if reward_a <= 0:
                reason = (
                    f"Price {round(last_close / price_scaler, 2)} has already exceeded "
                    f"Consolidation High {cons_high_raw / price_scaler:.2f} -- no reward remaining. "
                    f"Mandate: WAIT for pullback to VWAP ({floor_price}) before re-evaluating."
                )
            else:
                reason = (
                    f"Reward {reward_a / price_scaler:.2f} < 2x Risk {risk_a / price_scaler:.2f}. "
                    f"Consolidation High {cons_high_raw / price_scaler:.2f} too close to entry. "
                    f"Mandate: WAIT for pullback to VWAP ({floor_price})."
                )
            return ("HALT", f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY GATE FAILED (Profile A): {reason}")
    return None  # Gate passed


def _gate_capital_expectancy(p_code, risk_a, cons_high_raw, last_close,
                             hard_stop_raw, resistance_raw, atr_raw,
                             price_scaler, metrics):
    """CEG-001 — Capital Expectancy Gate [Spec Section 2.1].
    Returns None if passed, or (status, diagnostic) if failed."""
    _capital_rr = None
    _reward_label = None

    if p_code == "A" and risk_a >= (0.20 * atr_raw):
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - hard_stop_raw
        if _capital_risk > 0 and _capital_reward > 0:
            _capital_rr = _capital_reward / _capital_risk
            metrics["Capital_Reward_Risk"] = round(_capital_rr, 2)
            if _capital_rr < 1.0:
                return ("HALT", (
                    f"REJECT (reason: CAPITAL EXPECTANCY FAILED). CAPITAL EXPECTANCY FAILED: Capital R:R {round(_capital_rr, 2)} "
                    f"-- reward ${round(_capital_reward / price_scaler, 2)} vs. "
                    f"stop risk ${round(_capital_risk / price_scaler, 2)}. Minimum: 1.0."
                ))
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
        _capital_reward = cons_high_raw - last_close
        _capital_risk   = last_close - hard_stop_raw
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
        _capital_reward_b = resistance_raw - last_close
        _capital_risk_b   = last_close - hard_stop_raw
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
        metrics["Capital_RR_Label"] = _reward_label  # CEG-002: write label on Profile B
    else:
        # Profile C: not applicable
        metrics["Capital_Reward_Risk"] = None
        metrics["Capital_RR_Label"] = None

    return None  # Gate passed


# ==============================================================================
# MAIN ENGINE
# ==============================================================================



# ======================================================================
# RFT-001 PHASE 4: ProfileConfig Dataclass + Factory + Data Layer Extraction
# Spec §III.2 (ProfileConfig), §III.3 (Layer 1 - Data Fetch & Indicator Computation)
# ======================================================================
import asyncio
from dataclasses import dataclass

@dataclass(frozen=True)
class ProfileConfig:
    """Read-only profile-specific parameter configuration.

    Constructed once per run_tbs_engine() invocation via _build_config().
    Gates consume it; they never modify it. Collapses parameter-selection
    branches in the data layer into cfg.attribute lookups.

    RFT-001 Phase 4 | Spec §III.2
    """
    iq: int                       # indicator query index (-2 for A, -1 for B/C)
    min_bars_required: int        # data sufficiency threshold
    window_limit: int             # execution window staleness limit
    ff_threshold: int             # floor failure consecutive bar threshold
    ext_limit_trending: float     # extension limit when TRENDING (ATR multiplier)
    ext_limit_resolving: float    # extension limit when RESOLVING (ATR multiplier)
    ext_limit_etf: float          # extension limit for ETF (Profiles B/C)
    resistance_slice_start: int   # iloc start for resistance/focus window
    resistance_slice_end: int     # iloc end for resistance/focus window
    tf_resolution: str            # primary timeframe bar size
    tf_duration: str              # primary timeframe lookback
    ctx_resolution: str           # context chart bar size
    ctx_duration: str             # context chart lookback
    fb_max: float                 # THS Floor Buffer max
    ta_max: int                   # THS Trend Age max
    prev_bar_offset: int          # offset for morphology prev_high/prev_low
    required_ma_cols: tuple       # required MA columns for existence guard
    pb_upper_col: str             # column for pullback zone upper bound anchor


def _build_config(p_code):
    """Factory: build the correct ProfileConfig for a given p_code.

    RFT-001 Phase 4 | Spec §III.2
    """
    if p_code == "A":
        return ProfileConfig(
            iq=-2,
            min_bars_required=30,
            window_limit=4,
            ff_threshold=8,
            ext_limit_trending=1.5,
            ext_limit_resolving=1.5,
            ext_limit_etf=1.5,
            resistance_slice_start=-12,
            resistance_slice_end=-2,
            tf_resolution="1 hour",
            tf_duration="3 M",
            ctx_resolution="1 day",
            ctx_duration="12 M",
            fb_max=2.0,
            ta_max=30,
            prev_bar_offset=3,
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50"),
            pb_upper_col="ANCHOR",
        )
    elif p_code == "B":
        return ProfileConfig(
            iq=-1,
            min_bars_required=220,
            window_limit=5,
            ff_threshold=4,
            ext_limit_trending=1.0,
            ext_limit_resolving=0.5,
            ext_limit_etf=0.5,
            resistance_slice_start=-11,
            resistance_slice_end=-1,
            tf_resolution="1 day",
            tf_duration="2 Y",
            ctx_resolution="1 week",
            ctx_duration="5 Y",
            fb_max=3.0,
            ta_max=80,
            prev_bar_offset=2,
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50", "SMA_200"),
            pb_upper_col="EMA_21",
        )
    elif p_code == "C":
        return ProfileConfig(
            iq=-1,
            min_bars_required=220,
            window_limit=4,
            ff_threshold=4,
            ext_limit_trending=1.0,    # PE-CAL-1 §6.4: SMA 200 anchor, 1.0 ATR
            ext_limit_resolving=1.0,   # Same as trending for Profile C
            ext_limit_etf=0.5,
            resistance_slice_start=-11,
            resistance_slice_end=-1,
            tf_resolution="1 week",
            tf_duration="10 Y",
            ctx_resolution="1 month",
            ctx_duration="20 Y",
            fb_max=5.0,
            ta_max=60,
            prev_bar_offset=2,
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50", "SMA_200"),
            pb_upper_col="ANCHOR",
        )
    else:
        raise ValueError(f"Unknown p_code: {p_code}")


# ======================================================================
# RFT-001 PHASE 5: StateBundle Dataclass + State Classification Extraction
# Spec §III.4 (Layer 2 — State Classification)
# ======================================================================

@dataclass
class StateBundle:
    """All state classification results as a single typed object.

    Downstream layers receive this instead of loose local variables.
    ETF Logic Lock snapshots are fields of StateBundle, not loose
    variables that could be shadowed or incorrectly scoped.
    """
    # --- Core state classification ---
    is_trending: bool
    is_resolving: bool
    ma_stack_full: bool
    ma_squeeze: bool
    ema_stacked: bool

    # --- Scalars (from raw_metrics, included for downstream convenience) ---
    adx_t: float
    adx_t1: float
    di_plus: float
    di_minus: float
    atr_raw: float

    # --- ETF Logic Lock snapshots + composite entry flags ---
    _etf_entry_trending: bool
    _etf_entry_resolving: bool
    _entry_trending: bool
    _entry_resolving: bool

    # --- Derived classification flags ---
    _resolving_is_bearish: bool

    # --- Set after violated state detection (require post-convexity ANCHOR) ---
    is_reclaim: bool = False
    is_ambiguous: bool = False
    is_violated: bool = False
    is_floor_failure: bool = False
    floor_raw: float = 0.0
    consec_below: int = 0
    _reclaim_run: int = 0


def _classify_state(df, p_code, is_etf, cfg, raw_metrics):
    """Layer 2: State Classification.

    Absorbs the ~120-line ENGINE STATE CLASSIFICATION block from
    run_tbs_engine(). Receives the DataFrame, profile code, ETF flag,
    ProfileConfig, and raw_metrics dict. Returns a StateBundle.

    Signature adapted from spec (df, p_code, is_etf, cfg) to also
    accept raw_metrics for scalar extraction per §4.4 design intent.
    """
    # --- Scalar extraction from raw_metrics ---
    adx_t    = raw_metrics["adx_t"]
    adx_t1   = raw_metrics["adx_t1"]
    adx_t2   = raw_metrics["adx_t2"]
    di_plus  = raw_metrics["di_plus"]
    di_minus = raw_metrics["di_minus"]
    ma_squeeze = raw_metrics["ma_squeeze"]
    atr_raw  = raw_metrics["atr_raw"]

    last = df.iloc[cfg.iq]

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

    return StateBundle(
        is_trending=is_trending,
        is_resolving=is_resolving,
        ma_stack_full=ma_stack_full,
        ma_squeeze=ma_squeeze,
        ema_stacked=ema_stacked,
        adx_t=adx_t,
        adx_t1=adx_t1,
        di_plus=di_plus,
        di_minus=di_minus,
        atr_raw=atr_raw,
        _etf_entry_trending=_etf_entry_trending,
        _etf_entry_resolving=_etf_entry_resolving,
        _entry_trending=_entry_trending,
        _entry_resolving=_entry_resolving,
        _resolving_is_bearish=_resolving_is_bearish,
    )


def _fetch_and_compute(ticker, p_code, cfg, profile, is_etf_arg, mode, exchange, currency, convexity_class):
    """Layer 1: Data Fetch and Indicator Computation.

    Creates IB connection, fetches historical data, computes indicator stack,
    extracts scalar values, performs SSG-001 stop adjustment, and fetches
    context data. IB connection is created and closed within this function.

    Returns tuple[DataFrame, dict]:
        - DataFrame with full indicator stack
        - raw_metrics dict containing scalar values, metadata, and df_ctx.
          On early exit (error/halt): raw_metrics["_early_return"] = (status, diag, metrics)
          and DataFrame is None.

    RFT-001 Phase 4 | Spec §III.3
    """
    import asyncio
    import logging

    raw = {}  # raw_metrics accumulator

    # --- [MANDATE: CONCURRENCY INTEGRITY] ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 25 + (os.getpid() % 100)
    port = 4002 if mode.upper() == "INFO" else 4001

    ib = IB()

    # Suppress Error 162 (NYSENBBO routing)
    class _SuppressError162(logging.Filter):
        def filter(self, record):
            return 'Error 162' not in record.getMessage()
    logging.getLogger('ib_insync.wrapper').addFilter(_SuppressError162())

    metrics = {}  # [MANDATE: DOC 8 SEC 39] SSoT Handshake initialisation

    # EPX-001: PROXIMITY SIGNAL FIELD INITIALIZATION
    metrics["Proximity_Signal"]        = None
    metrics["Proximity_Blocking_Gate"] = None
    metrics["Proximity_Distance"]      = None
    metrics["Proximity_Target"]        = None
    metrics["Proximity_Note"]          = None

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
        ib.connect('127.0.0.1', port, clientId=unique_client_id)
        ib.reqMarketDataType(1)

        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)

        # --- [MANDATE: DOC 8 SEC 467] INDEPENDENT ASSET IDENTIFICATION ---
        _is_lse_etf = False
        is_etf = is_etf_arg  # start with caller's value; may be overridden by metadata
        details = ib.reqContractDetails(contract)
        if details:
            meta = details[0].longName.upper()
            etf_keywords = [
                'ETF', 'FUND', 'VANGUARD', 'VANG', 'ISHARES', 'UCITS',
                'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES'
            ]
            if any(key in meta for key in etf_keywords):
                is_etf = True

            qualified = details[0].contract
            primary_exch = getattr(qualified, 'primaryExchange', '') or getattr(details[0], 'primaryExch', '')
            if 'ETF' in primary_exch.upper():
                is_etf = True
                _is_lse_etf = True
            if primary_exch == 'NYSENBBO':
                qualified.primaryExchange = 'NYSE'
            contract = qualified

        res = cfg.tf_resolution
        dur = cfg.tf_duration

        bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True)

        # --- NYSENBBO RETRY GUARD ---
        nyse_retry_used = False
        if not bars and currency == "USD":
            contract.exchange        = 'NYSE'
            contract.primaryExchange = 'NYSE'
            bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True)
            nyse_retry_used = bool(bars)

        if not bars:
            raw["_early_return"] = ("ERROR", f"No data retrieved for {clean_ticker}", {})
            return None, raw

        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        # --- NYSE RETRY VOLUME PATCH ---
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
                    common_idx = df.index.intersection(df_vol.index)
                    if len(common_idx) > 10:
                        df.loc[common_idx, 'volume'] = df_vol.loc[common_idx, 'volume']
            except Exception:
                pass

        # --- DATA SUFFICIENCY GUARD ---
        if len(df) < cfg.min_bars_required:
            raw["_early_return"] = (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). Insufficient historical data: {len(df)} bars retrieved "
                f"(requires >= {cfg.min_bars_required} for Profile {p_code}). "
                f"Ticker may be too new or have limited exchange history for SMA_200 calculation.",
                metrics
            )
            return None, raw

        # --- TIMEFRAME NORMALIZATION ---
        bars_per_day = (
            8.0 if currency == "GBP" else
            8.5 if currency == "EUR" else
            6.5
        ) if "hour" in res else (
            1.0 / 5.0  if "week"  in res else
            1.0 / 21.0 if "month" in res else
            1.0
        )
        sma_20_length = int(20 * bars_per_day) if "hour" in res else (
            20  if "day"   in res else
            20  if "week"  in res else
            12  if "month" in res else
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
        for col in cfg.required_ma_cols:
            if col not in df.columns or df[col].isna().all():
                raw["_early_return"] = (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {col} is entirely NaN. "
                    f"Insufficient price history for this indicator on {clean_ticker}.",
                    metrics
                )
                return None, raw

        # [PE-18 / PE-24 FIX] Existence guard for ATR and Volume SMA columns.
        for ind_col in ['ATRr_14', 'vol_sma_9', 'vol_sma_20']:
            if ind_col not in df.columns or df[ind_col].isna().all():
                raw["_early_return"] = (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {ind_col} is entirely NaN or missing. "
                    f"pandas_ta may have failed for {clean_ticker}.",
                    metrics
                )
                return None, raw

        # --- COLUMN IDENTIFICATION ---
        adx_candidates = [c for c in df.columns if c.startswith('ADX') and 'DM' not in c]
        dmp_candidates = [c for c in df.columns if 'DMP' in c]
        dmn_candidates = [c for c in df.columns if 'DMN' in c]

        if not adx_candidates:
            raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). ADX column not found -- pandas_ta.adx() failed or insufficient data.", metrics)
            return None, raw
        if not dmp_candidates or not dmn_candidates:
            raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). Directional Movement columns (DI+/DI-) not found.", metrics)
            return None, raw

        adx_col = adx_candidates[0]
        dmp_col = dmp_candidates[0]
        dmn_col = dmn_candidates[0]

        # Scalar extraction using cfg.iq
        _iq = cfg.iq

        adx_t   = df[adx_col].iloc[_iq]
        adx_t1  = df[adx_col].iloc[_iq - 1]
        adx_t2  = df[adx_col].iloc[_iq - 2]
        di_plus  = df[dmp_col].iloc[_iq]
        di_minus = df[dmn_col].iloc[_iq]

        # [PE-19 FIX] NaN guard on ADX/DI values
        if any(pd.isna(v) for v in [adx_t, adx_t1, adx_t2, di_plus, di_minus]):
            raw["_early_return"] = (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). ADX/DI indicator values contain NaN at evaluated bar. "
                f"Insufficient data for trend classification on {clean_ticker}.",
                metrics
            )
            return None, raw

        # ADX SLOPE ACCELERATION
        adx_slope_t  = adx_t  - adx_t1
        adx_slope_t1 = adx_t1 - adx_t2
        adx_accel    = round(adx_slope_t - adx_slope_t1, 2)
        adx_accel_state = (
            "ACCELERATING" if adx_accel > 0.3 else
            "DECELERATING" if adx_accel < -0.3 else
            "CRUISING"
        )

        # --- MA SQUEEZE ---
        df['MA_Dist'] = abs(df['EMA_8'] - df['EMA_21'])
        df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])
        ma_squeeze    = bool(
            df['Squeeze'].iloc[_iq] and df['Squeeze'].iloc[_iq - 1] and df['Squeeze'].iloc[_iq - 2]
        )

        # Use last completed bar for Profile A (1H) to enforce BAR CLOSE cadence.
        last = df.iloc[cfg.iq]

        # --- PRE-COMPUTE RESISTANCE ---
        resistance_raw = float(df['high'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].max())

        # --- BASELINE ANCHOR COMPUTATION ---
        # Profile A: VWAP (state-independent)
        # Profile B: SMA_50 baseline (Convexity override to EMA_8 happens in run_tbs_engine after state classification)
        # Profile C: SMA_200 (state-independent)
        # ETF: baseline MA for the profile
        vwap_col = None
        if p_code == "A":
            df.ta.vwap(append=True)
            vwap_cols = [c for c in df.columns if 'VWAP' in c]
            if not vwap_cols:
                raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). VWAP column not found -- pandas_ta.vwap() failed or insufficient data.", metrics)
                return None, raw
            vwap_col = vwap_cols[0]
            df['ANCHOR'] = df[vwap_col]
        elif p_code == "B":
            # Baseline: SMA_50. Convexity override (EMA_8) applied in run_tbs_engine after state classification.
            if is_etf:
                df['ANCHOR'] = df['SMA_50']
            else:
                df['ANCHOR'] = df['SMA_50']  # baseline; run_tbs_engine may override to EMA_8
        elif p_code == "C":
            df['ANCHOR'] = df['SMA_200']

        # Re-read last row after ANCHOR column is computed
        last = df.iloc[cfg.iq]

        # --- SCALING & HARD STOP ---
        _is_lse_etf_local = _is_lse_etf
        price_scaler         = 1.0 if _is_lse_etf else (100.0 if currency == "GBP" else 1.0)
        actual_price         = last['close'] / price_scaler
        atr_raw              = float(last['ATRr_14'])
        structural_floor_raw = last['ANCHOR']
        hard_stop_raw = structural_floor_raw - (1.5 * atr_raw)

        # --- SSG-001: STRUCTURAL STOP AUDIT ---
        _ssg_adjusted = False
        _ssg_original_raw = None
        _ssg_reason = None
        if p_code == "A":
            _ssg_hourly_low = float(df['low'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].min())
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

        # --- CONTEXT DATA FETCH ---
        ctx_bars = ib.reqHistoricalData(contract, '', cfg.ctx_duration, cfg.ctx_resolution, 'TRADES', True)
        df_ctx = None
        if ctx_bars:
            df_ctx = util.df(ctx_bars)
            df_ctx.set_index('date', inplace=True)
            df_ctx.index = pd.to_datetime(df_ctx.index)
            df_ctx.sort_index(inplace=True)
            for ln in [8, 21]:   df_ctx.ta.ema(length=ln, append=True)
            for ln in [50, 200]: df_ctx.ta.sma(length=ln, append=True)
            df_ctx.ta.sma(close=df_ctx['volume'], length=9, append=True, col_names=('vol_sma_9',))

        # --- IB DISCONNECT ---
        if ib.isConnected():
            ib.disconnect()

        # --- POPULATE raw_metrics ---
        raw["is_etf"] = is_etf
        raw["_is_lse_etf"] = _is_lse_etf
        raw["clean_ticker"] = clean_ticker
        raw["currency"] = currency
        raw["exchange"] = exchange
        raw["p_exchange"] = p_exchange
        raw["metrics"] = metrics
        raw["adx_col"] = adx_col
        raw["dmp_col"] = dmp_col
        raw["dmn_col"] = dmn_col
        raw["adx_t"] = adx_t
        raw["adx_t1"] = adx_t1
        raw["adx_t2"] = adx_t2
        raw["di_plus"] = di_plus
        raw["di_minus"] = di_minus
        raw["adx_accel"] = adx_accel
        raw["adx_accel_state"] = adx_accel_state
        raw["ma_squeeze"] = ma_squeeze
        raw["resistance_raw"] = resistance_raw
        raw["price_scaler"] = price_scaler
        raw["actual_price"] = actual_price
        raw["atr_raw"] = atr_raw
        raw["structural_floor_raw"] = structural_floor_raw
        raw["hard_stop_raw"] = hard_stop_raw
        raw["_ssg_adjusted"] = _ssg_adjusted
        raw["_ssg_original_raw"] = _ssg_original_raw
        raw["_ssg_reason"] = _ssg_reason
        raw["bars_per_day"] = bars_per_day
        raw["vwap_col"] = vwap_col
        raw["df_ctx"] = df_ctx

        return df, raw

    except Exception as e:
        import traceback
        if ib.isConnected():
            ib.disconnect()
        raw["_early_return"] = ("ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", {})
        return None, raw





# [RFT-001 Phase 6A] _proximity_audit promoted from nested to top-level.
# All former closure variables now passed explicitly via keyword arguments.
def _proximity_audit(_prx_metrics, _prx_status, _prx_diag, state, mode,
                     p_code, is_etf, last, prev_high, resistance_raw,
                     ext_limit, atr_dist, window_count, window_limit,
                     cons_high_raw, hard_stop_raw, price_scaler,
                     prox_anchor, df, structural_floor_raw):
    """Write 5 Proximity_* fields to metrics. EPX-001 post-verdict audit.

    Promoted to top-level in Phase 6. Previously a nested function inside
    run_tbs_engine with closure over local variables.
    """

    # --- Step 1: Eligibility (Section IV.2, Step 1) ---
    if _prx_status == "PASS":
        return
    if mode.upper() == "MONITOR":
        return  # DQ-5: suppress in Position Monitor mode
    if p_code == "C":
        return  # Profile C excluded (Section 1.1)

    # --- Step 2: Identify blocking gate (Section IV.2, Step 2) ---
    _reason = None
    if "reason:" in _prx_diag:
        try:
            _r_start = _prx_diag.index("reason:") + 8
            _r_end   = _prx_diag.index(")", _r_start)
            _reason  = _prx_diag[_r_start:_r_end].strip()
        except ValueError:
            return  # malformed diagnostic

    if _reason is None:
        return

    # --- Step 3: Gate classification (Section II) ---
    _PROXIMITY_MAP = {
        "EXTENDED":                   "EXTENSION",
        "MID-RANGE (ADX < 20)":       "ADX_THRESHOLD_20",
        "NOT IN PULLBACK ZONE":       ("VWAP_PULLBACK" if p_code == "A"
                                       else "SMA50_PULLBACK"),
        "NO BREAKOUT":                "BREAKOUT_RESISTANCE",
        "PROFILE A RESOLVING BLOCK":  "ADX_THRESHOLD_25",
    }

    _blocking_gate = _PROXIMITY_MAP.get(_reason)

    # RECLAIM_2_OF_3: floor failure with exactly 2 reclaim bars
    if _reason == "FLOOR FAILURE" and state._reclaim_run == 2:
        _blocking_gate = "RECLAIM_2_OF_3"

    if _blocking_gate is None:
        return  # structural gate — null defaults are correct

    # --- Step 4: Structural gate filter (Section IV.2, Step 3) ---
    # Forward-looking: would all structural gates pass if this one
    # proximity gate were hypothetically clear?

    # Floor integrity (skip for RECLAIM — that IS the floor scenario)
    if _blocking_gate != "RECLAIM_2_OF_3":
        if state.is_floor_failure or state.is_violated:
            return

    # DI Dominance
    _di_blocked = False
    if state.di_minus > state.di_plus:
        if p_code == "A" and state.ema_stacked:
            pass  # Profile A EMA exemption
        elif p_code == "B" and state._entry_trending and state.ma_stack_full:
            pass  # Profile B TRENDING exemption
        else:
            _di_blocked = True
    if _di_blocked:
        return

    # Gap Trap
    if ((last['open'] > (prev_high + (0.5 * state.atr_raw)))
            and (last['close'] < last['open'])):
        return

    # Window Expired
    if window_count > window_limit:
        return

    # MA Squeeze (structural — distinct from ADX < 20)
    if state.ma_squeeze:
        return

    # Volume Climax (evaluate from available data)
    _climax_df_ck = df.iloc[:-1] if p_code == "A" else df
    if (not pd.isna(_climax_df_ck['vol_sma_9'].iloc[-1])):
        _climax_ck, _ = check_climax_history(_climax_df_ck)
        if _climax_ck:
            return

    # Profile A Expectancy (structural — forward check)
    if p_code == "A" and _blocking_gate != "RECLAIM_2_OF_3":
        _pa_reward = ((cons_high_raw - last['close'])
                      if cons_high_raw is not None else 0)
        _pa_risk   = last['close'] - last['ANCHOR']
        _pa_grace  = 0.15 * state.atr_raw if state.atr_raw > 0 else 0
        if _pa_risk < -_pa_grace:
            return  # floor violation
        _pa_risk = max(_pa_risk, 0)
        if _pa_risk == 0:
            pass  # floor-exact — PE-CAL-2 handles
        elif _pa_risk < (0.20 * state.atr_raw):
            _pa_hs_risk = last['close'] - hard_stop_raw
            if (_pa_hs_risk > 0 and _pa_reward > 0
                    and _pa_reward / _pa_hs_risk < 2.0):
                return
        else:
            if _pa_reward < (2.0 * _pa_risk):
                return
        # CEG-001 forward check
        if _pa_risk >= (0.20 * state.atr_raw):
            _pa_cap_r = ((cons_high_raw - last['close'])
                         if cons_high_raw else 0)
            _pa_cap_k = last['close'] - hard_stop_raw
            if (_pa_cap_k > 0 and _pa_cap_r > 0
                    and _pa_cap_r / _pa_cap_k < 1.0):
                return

    # --- Step 4b: State-qualification guard (EPX-001-OBS-2) ---
    if _blocking_gate in ("VWAP_PULLBACK", "SMA50_PULLBACK"):
        if not state._entry_trending:
            return
    elif _blocking_gate == "EXTENSION":
        if not (state._entry_trending or state._entry_resolving):
            return
    elif _blocking_gate == "BREAKOUT_RESISTANCE":
        if not state._entry_resolving:
            return

    # --- Step 5: Count proximity blockers (Section IV.2, Step 4) ---
    _pb_upper_ck = ((last['EMA_21'] + (0.5 * state.atr_raw)) if p_code == "B"
                    else (last['ANCHOR'] + (0.5 * state.atr_raw)))
    _at_pb_ck    = ((last['close'] >= last['ANCHOR'])
                    and (last['close'] <= _pb_upper_ck))
    _cvx_sup     = last['ANCHOR'] if is_etf else last['EMA_8']
    _at_bo_ck    = ((last['close'] > resistance_raw)
                    and (last['close'] > _cvx_sup))

    _blockers = []

    # ADX_THRESHOLD_20
    if state.adx_t < 20:
        _blockers.append("ADX_THRESHOLD_20")

    # ADX_THRESHOLD_25 (Profile A RESOLVING → needs TRENDING)
    if (p_code == "A" and state._entry_resolving and not state._entry_trending
            and not state.ma_squeeze and state.adx_t >= 20 and state.adx_t < 25):
        _blockers.append("ADX_THRESHOLD_25")

    # EXTENSION — account for breakout bar exemption
    _is_bo_bar_ck = ((last['close'] > resistance_raw)
                     if p_code == "B" else False)
    _eff_ext = (1.5 if (_is_bo_bar_ck and not state.is_trending
                        and state._entry_resolving) else ext_limit)
    if atr_dist > _eff_ext:
        _blockers.append("EXTENSION")

    # PULLBACK (TRENDING but above pullback zone, above floor)
    if (state._entry_trending and not _at_pb_ck
            and last['close'] >= last['ANCHOR']):
        _blockers.append(
            "VWAP_PULLBACK" if p_code == "A" else "SMA50_PULLBACK")

    # BREAKOUT_RESISTANCE (RESOLVING, below resistance, non-A)
    if (state._entry_resolving and not state._entry_trending
            and p_code != "A" and not _at_bo_ck):
        _blockers.append("BREAKOUT_RESISTANCE")

    # RECLAIM_2_OF_3
    if state.is_floor_failure and state._reclaim_run == 2:
        _blockers.append("RECLAIM_2_OF_3")

    # DQ-2: strict single-gate rule
    if len(_blockers) != 1:
        return
    if _blockers[0] != _blocking_gate:
        return  # sanity — identified blocker must match

    # --- Step 6: Distance computation (Section III + VII DQ-1) ---
    _dist      = None
    _target    = None
    _threshold = None
    _note_ctx  = ""

    if _blocking_gate == "VWAP_PULLBACK":
        _dist      = (last['close'] - _pb_upper_ck) / state.atr_raw
        _target    = round(_pb_upper_ck / price_scaler, 2)
        _threshold = 0.5
        _note_ctx  = (f"{_dist:.2f} ATR above pullback zone "
                      f"({_target}). "
                      f"One hourly pullback creates valid entry.")

    elif _blocking_gate == "SMA50_PULLBACK":
        _dist      = (last['close'] - _pb_upper_ck) / state.atr_raw
        _target    = round(_pb_upper_ck / price_scaler, 2)
        _threshold = 0.5
        _note_ctx  = (f"{_dist:.2f} ATR above pullback zone "
                      f"({_target}). "
                      f"One daily pullback creates valid entry.")

    elif _blocking_gate == "EXTENSION":
        _dist      = atr_dist - _eff_ext
        _target    = round(
            (prox_anchor + (_eff_ext * state.atr_raw)) / price_scaler, 2)
        _threshold = 0.3
        _tf_label  = "hourly" if p_code == "A" else "daily"
        _note_ctx  = (f"{_dist:.2f} ATR past extension limit "
                      f"({_eff_ext}). One {_tf_label} pullback "
                      f"into valid zone.")

    elif _blocking_gate == "BREAKOUT_RESISTANCE":
        _dist      = (resistance_raw - last['close']) / state.atr_raw
        _target    = round(resistance_raw / price_scaler, 2)
        _threshold = 0.3
        _note_ctx  = (f"{_dist:.2f} ATR below resistance ({_target}). "
                      f"One daily close above resistance triggers "
                      f"breakout.")

    elif _blocking_gate == "ADX_THRESHOLD_20":
        _dist      = 20.0 - state.adx_t
        _target    = 20.0
        _threshold = 1.5
        _note_ctx  = (f"{_dist:.2f} ADX points below 20 threshold. "
                      f"ADX acceleration could cross on next bar.")

    elif _blocking_gate == "ADX_THRESHOLD_25":
        _dist      = 25.0 - state.adx_t
        _target    = 25.0
        _threshold = 1.5
        _note_ctx  = (f"{_dist:.2f} ADX points below 25 "
                      f"(TRENDING transition). ADX acceleration "
                      f"could cross on next bar.")

    elif _blocking_gate == "RECLAIM_2_OF_3":
        # DQ-4: Heuristic guard
        if not (state.ma_stack_full and state.adx_t > 20
                and state.di_plus > state.di_minus):
            return
        _dist      = None  # bar-count based
        _target    = round(structural_floor_raw / price_scaler, 2)
        _threshold = None
        _note_ctx  = (f"1 bar remaining. Next close above floor "
                      f"({_target}) completes 3-bar reclaim.")

    else:
        return  # unhandled gate

    # Threshold check (skip for bar-count gates)
    if _dist is not None and _threshold is not None:
        if _dist < 0:
            return  # gate not actually blocking
        if _dist > _threshold:
            return  # beyond proximity range

    # --- Step 7: Write APPROACHING (Section V) ---
    _ths_val = _prx_metrics.get('Trend_Health_Score', 0)

    _prx_metrics["Proximity_Signal"]        = "APPROACHING"
    _prx_metrics["Proximity_Blocking_Gate"]  = _blocking_gate
    _prx_metrics["Proximity_Distance"]       = (round(_dist, 2)
                                                if _dist is not None
                                                else None)
    _prx_metrics["Proximity_Target"]         = _target
    _prx_metrics["Proximity_Note"]           = (
        f"APPROACHING: {_note_ctx} "
        f"All structural gates PASS. "
        f"THS: {round(_ths_val)}."
    )



# [RFT-001 Phase 7] Layer 4: Trigger Identification
# Extracts the Priority 1-4 trigger chain and PASS-only enrichment (PE-30,
# Focus Chart, ENG-002) into a top-level function per spec §III.6.
# Receives gate cascade result and determines final (status, diagnostic).
def _identify_trigger(state, cfg, p_code, is_etf, metrics,
                      result_status, result_diagnostic,
                      last, df, resistance_raw, resistance_display,
                      floor_price, hard_stop, chart_ref,
                      conviction_state, price_scaler,
                      _resistance_suppressed, _capital_rr, _reward_label,
                      _p1_resistance_note, _p1_reward_risk_note,
                      profile, clean_ticker, adx_col, dmp_col, dmn_col,
                      chart_dir):
    """Layer 4: Identify trigger type from state and gate cascade result.

    Wraps the Priority 1-4 trigger chain (RECLAIM, TRENDING/PULLBACK,
    RESOLVING/BREAKOUT, AMBIGUOUS) and PASS-only enrichment (PE-30,
    Focus Chart rendering, ENG-002 Fibonacci Confluence).

    If result_status is already set by the gate cascade (HALT), the
    trigger chain is skipped and the existing result passes through.

    Args:
        state: StateBundle from Layer 2.
        cfg: ProfileConfig from Layer 1.
        p_code: Profile code ("A", "B", "C").
        is_etf: Whether the ticker is an ETF.
        metrics: Metrics dict (mutated — PE-30, ENG-002 writes).
        result_status: Gate cascade result ("HALT" or None).
        result_diagnostic: Gate cascade diagnostic (str or None).
        last: Evaluated bar (DataFrame row).
        df: Full DataFrame.
        resistance_raw: Raw resistance level.
        resistance_display: Display-scaled resistance.
        floor_price: Display-scaled structural floor.
        hard_stop: Display-scaled hard stop.
        chart_ref: Chart reference string for diagnostics.
        conviction_state: Conviction label (HIGH/LOW).
        price_scaler: Currency scaling factor.
        _resistance_suppressed: Whether resistance < current price.
        _capital_rr: Capital Reward/Risk ratio.
        _reward_label: Capital R:R label string.
        _p1_resistance_note: Phase 1 Resistance_Note for PE-31 restore.
        _p1_reward_risk_note: Phase 1 Reward_Risk_Note for PE-31 restore.
        profile: Profile name string (for Focus Chart).
        clean_ticker: Cleaned ticker symbol (for Focus Chart).
        adx_col: ADX column name (for Focus Chart).
        dmp_col: +DI column name (for Focus Chart).
        dmn_col: -DI column name (for Focus Chart).
        chart_dir: Chart output directory (for Focus Chart).

    Returns:
        tuple: (status, diagnostic) — "PASS" or "HALT" with diagnostic string.
    """

    # Current-bar position flags (independent of window-reset columns)
    # [PE-CAL-1 FIX §6.1] Pullback zone upper bound uses cfg.pb_upper_col.
    # Floor (ANCHOR) remains the lower bound. Profile B widens the zone to
    # encompass the natural pullback channel between SMA 50 and EMA 21.
    _pb_upper_cur = last[cfg.pb_upper_col] + (0.5 * state.atr_raw)
    at_pullback_zone = (
            (last['close'] >= last['ANCHOR']) and
            (last['close'] <= _pb_upper_cur)
    )

    # [MANDATE: DOC 2 SEC VI.2] Convex Support: Price > EMA 8 required at breakout.
    # [PE-BUG-1 FIX] ETF Exemption: Convexity Protocol is bypassed (Doc 6 §3.4.1).
    # ETF breakout validates against baseline floor (ANCHOR) instead of EMA 8.
    _convex_support_level = last['ANCHOR'] if is_etf else last['EMA_8']
    at_breakout = (
            (last['close'] > resistance_raw) and
            (last['close'] > _convex_support_level)
    )

    # ==================================================================
    # [PE-31] RESTORE Phase 1 diagnostic strings for Phase 4.
    # ==================================================================
    if result_status is None:
        if metrics.get("Resistance_Note") is None:
            metrics["Resistance_Note"] = _p1_resistance_note
        if metrics.get("Reward_Risk_Note") is None:
            metrics["Reward_Risk_Note"] = _p1_reward_risk_note

    # ---- PRIORITY 1: RECLAIM PROTOCOL  [Doc 2 Sec VI.3] ----
    if result_status is None and state.is_reclaim:
        # State quality gate: reclaim is only a valid re-entry signal if the
        # underlying directional state is confirmed (TRENDING or RESOLVING).
        if not (state._entry_trending or state._entry_resolving):
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: RECLAIM WITHOUT REGIME). RECLAIM DETECTED but state AMBIGUOUS: ADX {state.adx_t:.1f} -- MA stack incomplete "
                                 f"and no confirmed 3-bar ADX slope. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                                 f"but directional regime not active. Mandate: HARD WAIT. "
                                 f"Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.")
        else:
            result_status = "PASS"
            _reclaim_state = "TRENDING" if state._entry_trending else "RESOLVING"
            _reclaim_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: RECLAIM | state: {_reclaim_state} | "
                f"reward: {_reclaim_reward} | trigger: BAR CLOSE ONLY). "
                f"Current bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                f"after {state.consec_below} prior bar(s) below Floor. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close above {floor_price} before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )

    # ---- PRIORITY 2: TRENDING STATE -- Standard/Pullback Protocol  [Doc 2 Sec VI.1] ----
    if result_status is None and state._entry_trending:
        if at_pullback_zone:
            result_status = "PASS"
            _pb_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: PULLBACK | state: TRENDING | "
                f"reward: {_pb_reward} | trigger: BAR CLOSE ONLY). "
                f"Price {round(last['close'] / price_scaler, 2)} within pullback zone "
                f"[{floor_price} -- {round(_pb_upper_cur / price_scaler, 2)}]. "
                f"ADX: {state.adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close within pullback zone before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )
        else:
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: NOT IN PULLBACK ZONE). TRENDING (ADX {state.adx_t:.1f}) -- price not in pullback zone. "
                                 f"Mandate: WAIT for Floor Test at {floor_price}.")

    # ---- PRIORITY 3: RESOLVING STATE -- Convexity/Breakout Protocol  [Doc 2 Sec VI.2] ----
    if result_status is None and state._entry_resolving:
        # [GENUINE PROFILE LOGIC] Profile A Convexity Protocol block.
        # Profile A requires TRENDING state; RESOLVING is not sufficient.
        # This is a genuine behavioural difference, not a parameter selection.
        if p_code == "A":
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: PROFILE A RESOLVING BLOCK). CONVEXITY PROTOCOL BLOCKED (Profile A): "
                                 f"Profile A requires TRENDING state for pullback entry. "
                                 f"Current: RESOLVING (ADX {state.adx_t:.1f} -- below 25 threshold). "
                                 f"Mandate: WAIT for ADX > 25 and TRENDING state to enable pullback entry path. "
                                 f"Floor: {floor_price}.")
        elif at_breakout:
            result_status = "PASS"
            sizing  = "Full Unit" if conviction_state.startswith("HIGH") else "50% Unit (Low Conviction)"
            _bo_reward = (
                f"{_reward_label} [{_capital_rr:.2f}]"
                if _reward_label and _capital_rr is not None
                else "N/A"
            )
            result_diagnostic = (
                f"PRE-APPROVED (entry: BREAKOUT | state: RESOLVING | "
                f"reward: {_bo_reward} | trigger: INTRADAY). "
                f"Price {round(last['close'] / price_scaler, 2)} closed above resistance "
                f"{round(resistance_raw / price_scaler, 2)}. "
                f"ADX: {state.adx_t:.1f}. Sizing: {sizing}. "
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
            result_status = "HALT"
            result_diagnostic = (f"WAIT (reason: NO BREAKOUT). RESOLVING (ADX {state.adx_t:.1f}) -- {reason} at "
                                 f"{round(resistance_raw / price_scaler, 2)}. "
                                 f"Mandate: WAIT for Consolidation Range violation.")

    # ---- PRIORITY 4: AMBIGUOUS (ADX 20-25, MA stack incomplete) ----
    if result_status is None:
        result_status = "HALT"
        result_diagnostic = (f"WAIT (reason: AMBIGUOUS STATE). ENGINE STATE AMBIGUOUS: ADX {state.adx_t:.1f} > 20 but TRENDING not confirmed "
                             f"(MA stack incomplete or ADX < 25). Mandate: HARD WAIT.")

    # ==================================================================
    # PASS-ONLY SECTIONS: PE-30, Focus Chart, ENG-002
    # These only execute when the cascade result is PASS.
    # ==================================================================

    if result_status == "PASS":
        # ==================================================================
        # PE-30: Align Resistance_Note with BREAKOUT verdict
        # ==================================================================
        if _resistance_suppressed and at_breakout:
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
            result_diagnostic += f" | Focus: {focus_path}"
        except Exception as focus_err:
            result_diagnostic += f" | [Focus chart skipped: {str(focus_err)}]"

        # ======================================================================
        # ENG-002: FIBONACCI RETRACEMENT CONFLUENCE DIAGNOSTIC  [Amendment ENG-002]
        # Scope: Profile B (TREND), TRENDING state only. Not computed for
        # Profile A, Profile C, RESOLVING state, or ETFs.
        # NON-GATE: informational only. No verdict or gate impact.
        # [Phase 6 note: ENG-002 metrics writes stay with computation per spec §III.6]
        # Only runs on PASS paths (original behavior: HALT early-returns skipped this).
        # ======================================================================
        if p_code == "B" and state._entry_trending and not is_etf:
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

    return result_status, result_diagnostic


# [RFT-001 Phase 6C] Layer 5: Output Assembly
# Consolidates post-evaluation metric population into a single-pass function.
# [Phase 7 NOTE] PE-7b, Bug #33, and ENG-001 remain in run_tbs_engine at their
# original positions (before gates). Option B (relocate to _assemble_output) was
# attempted but created a behavioral delta: ENG-001 reads Profit_Target before
# gates write to it. Moving ENG-001 post-gates changed RN_Target_Proximity from
# None to "CLEAR" on several paths. The ordering dependency is NOT resolved.
# THS computation and proximity audit are consolidated here.
def _assemble_output(metrics, result_status, result_diagnostic, state, cfg,
                     last, df, window_count, _is_c3, _prx_ctx):
    """Layer 5: Assemble final output tuple after all gates and triggers.

    Receives the accumulated evaluation results and produces the final
    (status, diagnostic, metrics) return tuple. Owns THS computation
    and proximity audit.

    Note: Bug #33, PE-7b suppression, and ENG-001 remain in run_tbs_engine
    at their original pre-gate positions. ENG-001 reads Profit_Target before
    gates populate it — relocating to Layer 5 would change observed values.

    Args:
        metrics: Partially populated metrics dict (Layer 1 + run_tbs_engine writes).
        result_status: "PASS" or "HALT" from cascade/trigger chain.
        result_diagnostic: Diagnostic string from cascade/trigger chain.
        state: StateBundle from Layer 2.
        cfg: ProfileConfig from Layer 1.
        last: Evaluated bar (DataFrame row).
        df: Full DataFrame (for SMA_200 column check).
        window_count: Bars since last structural event.
        _is_c3: Whether convexity class is C3.
        _prx_ctx: Context dict for _proximity_audit call.

    Returns:
        tuple: (status, diagnostic, metrics)
    """

    # --- THS COMPUTATION [MODULE G] ---
    # Composite 0-100 metric from four sub-scores. Read-only — does not
    # alter any gate, exit, or verdict.
    # [RFT-001 Phase 6C] Moved from inline in run_tbs_engine to Layer 5.

    # Component 1: Floor Buffer (ATR distance price → structural floor)
    _fb_atr = (last['close'] - state.floor_raw) / state.atr_raw if state.atr_raw > 0 else 0
    _fb_max = cfg.fb_max
    _fb = _clamp(_fb_atr / _fb_max, 0, 1) * 100 if _fb_atr > 0 else 0

    # Component 2: Directional Momentum (ADX strength + DI spread)
    _adx_s = _clamp((state.adx_t - 15) / 30, 0, 1)
    _di_s  = _clamp((state.di_plus - state.di_minus) / 20, 0, 1)
    _dm    = (_adx_s * 0.6 + _di_s * 0.4) * 100

    # Component 3: Trend Age (bars since window reset — window_count IS the age)
    _ta_max  = cfg.ta_max
    _ta_bars = window_count if window_count != 99 else _ta_max
    _ta      = _clamp(1 - (_ta_bars / _ta_max), 0, 1) * 100

    # Component 4: Structure Quality (MA stack integrity + EMA separation)
    _stk = ((15 if last['close'] > last['EMA_8']  else 0)
            + (15 if last['EMA_8']  > last['EMA_21'] else 0)
            + (10 if last['EMA_21'] > last['SMA_50'] else 0)
            + (10 if ('SMA_200' in df.columns and not pd.isna(last['SMA_200'])
                      and last['SMA_50'] > last['SMA_200']) else 0))
    _ema_gap = abs(last['EMA_8'] - last['EMA_21']) / state.atr_raw if state.atr_raw > 0 else 0
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

    # --- PROXIMITY AUDIT ---
    # Called exactly once, after all metrics are populated.
    # [RFT-001 Phase 6C] Consolidated from 32 scattered calls to single call here.
    _proximity_audit(metrics, result_status, result_diagnostic, **_prx_ctx)

    return result_status, result_diagnostic, metrics


def run_tbs_engine(ticker, profile="TREND", is_etf=False, mode="INFO",
                   exchange="SMART", currency="USD", convexity_class=None):

    # --- [CONVEXITY] Input validation (Redesign Proposal §4.1 / Execution Map §VI) ---
    _VALID_CONVEXITY = {None, "C1", "C2", "C3"}
    if convexity_class not in _VALID_CONVEXITY:
        return "ERROR", f"INVALID CONVEXITY CLASS: '{convexity_class}'. Valid: None, 'C1', 'C2', 'C3'.", {}
    _is_c3 = (convexity_class == "C3")

    # --- PROFILE MAPPING ---
    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code    = p_mapping.get(profile.upper())
    if p_code is None:
        return "ERROR", (f"INVALID PROFILE: '{profile}' not recognised. "
                         f"Valid: SWING (A), TREND (B), WEALTH (C)."), {}

    # --- [RFT-001 Phase 4] Build ProfileConfig ---
    cfg = _build_config(p_code)

    # --- [RFT-001 Phase 4] Layer 1: Data Fetch & Indicator Computation ---
    df, raw_metrics = _fetch_and_compute(
        ticker, p_code, cfg, profile, is_etf, mode, exchange, currency, convexity_class
    )

    # Handle early returns from data layer
    if df is None:
        _er = raw_metrics.get("_early_return")
        if _er:
            return _er[0], _er[1], _er[2] if len(_er) > 2 else {}
        return "ERROR", "Unknown data layer failure", {}

    # --- Unpack raw_metrics into local variables ---
    # [RFT-001 Phase 5] State-classification scalars (adx_t, adx_t1, adx_t2,
    # di_plus, di_minus, ma_squeeze, atr_raw) are now extracted inside
    # _classify_state() and accessed via state.attribute. Only non-state
    # variables remain unpacked here.
    is_etf           = raw_metrics["is_etf"]
    _is_lse_etf      = raw_metrics["_is_lse_etf"]
    clean_ticker     = raw_metrics["clean_ticker"]
    currency         = raw_metrics["currency"]
    p_exchange       = raw_metrics.get("p_exchange", "")
    metrics          = raw_metrics["metrics"]
    adx_col          = raw_metrics["adx_col"]
    dmp_col          = raw_metrics["dmp_col"]
    dmn_col          = raw_metrics["dmn_col"]
    adx_accel        = raw_metrics["adx_accel"]
    adx_accel_state  = raw_metrics["adx_accel_state"]
    resistance_raw   = raw_metrics["resistance_raw"]
    price_scaler     = raw_metrics["price_scaler"]
    actual_price     = raw_metrics["actual_price"]
    structural_floor_raw = raw_metrics["structural_floor_raw"]
    hard_stop_raw    = raw_metrics["hard_stop_raw"]
    _ssg_adjusted    = raw_metrics["_ssg_adjusted"]
    _ssg_original_raw = raw_metrics["_ssg_original_raw"]
    _ssg_reason      = raw_metrics["_ssg_reason"]
    bars_per_day     = raw_metrics["bars_per_day"]
    vwap_col         = raw_metrics["vwap_col"]
    df_ctx           = raw_metrics["df_ctx"]

    # --- [RFT-001 Phase 5] Layer 2: State Classification ---
    state = _classify_state(df, p_code, is_etf, cfg, raw_metrics)

    try:
        script_dir   = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        chart_dir    = os.path.join(project_root, "charts")
        if not os.path.exists(chart_dir):
            os.makedirs(chart_dir)

        # [MANDATE: CHART INTEGRITY] Purge all existing charts
        for suffix in ("_primary.png", "_context.png", "_focus.png"):
            try:
                os.remove(os.path.join(chart_dir, f"{clean_ticker}{suffix}"))
            except FileNotFoundError:
                pass


        # Re-derive last bar (same as _fetch_and_compute used)
        last = df.iloc[cfg.iq]

        # ======================================================================
        # ENGINE STATE CLASSIFICATION  [MANDATE: DOC 2 SEC 4.2]
        # [RFT-001 Phase 5] Extracted into _classify_state() + StateBundle.
        # state = _classify_state(...) called after _fetch_and_compute() above.
        # All state fields now accessed via state.attribute.
        # ======================================================================

        # ======================================================================

        # ======================================================================
        # STRUCTURAL FLOOR MAPPING  [MANDATE: DOC 2 SEC 4.1]
        # Baseline ANCHOR was set in _fetch_and_compute():
        #   Profile A = VWAP, Profile B = SMA_50, Profile C = SMA_200
        # Profile B Convexity override: if RESOLVING and not TRENDING and ema_stacked,
        # re-assign ANCHOR to EMA_8 (non-ETF only).
        # ETF Profile B/C: baseline MA is immutable (ETF Logic Lock).
        # ======================================================================
        if p_code == "B" and not is_etf:
            _convexity_eligible = state.is_resolving and not state.is_trending and state.ema_stacked
            if _convexity_eligible:
                df['ANCHOR'] = df['EMA_8']
                # Re-derive dependent values after ANCHOR override
                last = df.iloc[cfg.iq]
                structural_floor_raw = last['ANCHOR']
                hard_stop_raw = structural_floor_raw - (1.5 * state.atr_raw)

        # Re-read last row in case ANCHOR changed
        last = df.iloc[cfg.iq]

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
            prox_anchor = last['EMA_8'] if (state.is_resolving and not state.is_trending) else last['EMA_21']

        atr_dist = (last['close'] - prox_anchor) / state.atr_raw

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
        # [RFT-001 Phase 4] Extension limit from cfg + state-dependent selection
        if is_etf:
            ext_limit = cfg.ext_limit_etf
        elif state.is_trending:
            ext_limit = cfg.ext_limit_trending
        else:
            ext_limit = cfg.ext_limit_resolving

        # --- ADV  [MANDATE: DOC 2 SEC II] ---
        adv_20 = float((df['vol_sma_20'].iloc[-1] * actual_price) * bars_per_day)

        # ======================================================================
        # MORPHOLOGY -- MODIFIERS A, B, C, D  [MANDATE: DOC 2 SEC VII]
        # Visual estimation strictly prohibited; all conditions mathematical.
        # ======================================================================

        total_range = last['high'] - last['low']
        real_body   = abs(last['close'] - last['open'])
        # Profile A last = df.iloc[-2], so "previous bar" is one further back.
        prev_high   = df['high'].iloc[-cfg.prev_bar_offset]
        prev_low    = df['low'].iloc[-cfg.prev_bar_offset]

        # [MANDATE: BAR-CLOSE CADENCE] For Profile A, vol_sma_9 must reference the
        # last COMPLETED bar (iloc[-2]). Using iloc[-1] includes the live opening-stub
        # bar -- its partial volume deflates the SMA, making Modifiers B and D
        # marginally easier to trigger than the mandate intends.
        # The climax filter applies the same discipline (passes df.iloc[:-1]).
        _vol_sma9_ref = df['vol_sma_9'].iloc[cfg.iq]

        # Modifier A: Structural Rejection Bar
        mod_a = (
                (total_range > (0.5 * state.atr_raw)) and
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
                (abs(last['close'] - last['ANCHOR']) <= (0.5 * state.atr_raw))
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
            "LOW (Range < 1.2 ATR)"  if total_range < (1.2 * state.atr_raw)
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
        _vw_slice = df.iloc[cfg.resistance_slice_start:cfg.resistance_slice_end]
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
        window_limit  = cfg.window_limit
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
        i0 = cfg.iq  # evaluated bar index (Profile A uses last completed bar)
        current_above_floor = df['close'].iloc[i0] >= df['ANCHOR'].iloc[i0]

        # [PE-29] Floor failure threshold scaled by profile bar frequency.
        # Profile A (hourly): 8 bars (~1 full session) before declaring structural break.
        # Profile B (daily):  4 bars (~1 week) -- original threshold, appropriate for daily.
        # Profile C (weekly): 4 bars (~1 month) -- 4 weeks is already substantial.
        # The violation range (below threshold) and lookback depth scale accordingly.
        _ff_threshold = cfg.ff_threshold
        _ff_lookback  = _ff_threshold + 1  # scan depth: threshold + 1 for boundary detection

        # Grace buffer: a bar must close more than 0.15 ATR below the floor to count
        # as a "below" bar. This prevents micro-wicks and hairline breaches from
        # triggering violated/failure states on stocks hugging their floor.
        grace = 0.15 * float(df['ATRr_14'].iloc[i0]) if not pd.isna(df['ATRr_14'].iloc[i0]) else 0

        if current_above_floor:
            # Current bar reclaimed. Count consecutive below-floor bars among
            # PRIOR bars (k=2 is the bar before current, k=3 is two bars ago...).
            state.consec_below = 0
            for offset in range(1, _ff_lookback):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    state.consec_below += 1
                else:
                    break  # Streak broken -- stop counting
            state.is_violated     = False                                        # Current bar is healthy
            state.is_reclaim      = (1 <= state.consec_below <= (_ff_threshold - 1))  # Prior bars below but under threshold = Reclaim
            state.is_floor_failure = (state.consec_below >= _ff_threshold)             # Structural failure
        else:
            # Current bar is below floor. Count the current streak including it.
            state.consec_below = 0
            for offset in range(0, _ff_lookback):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    state.consec_below += 1
                else:
                    break
            state.is_violated      = (1 <= state.consec_below <= (_ff_threshold - 1))  # Waiting for Reclaim
            state.is_reclaim       = False                                        # Current bar not above floor
            state.is_floor_failure = (state.consec_below >= _ff_threshold)              # Structural failure

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
        state._reclaim_run = 0  # Tracks consecutive above-floor bars for PE-25 messaging
        if current_above_floor:
            if state.is_floor_failure:
                # Original counter detected floor failure (4+ prior bars below).
                # Current bar is the FIRST reclaim bar.
                state._reclaim_run = 1
            elif not state.is_violated:
                # No immediate failure detected by simple counter.
                # Scan deeper: count consecutive above-floor closes from i0 backward.
                for _r_off in range(0, _ff_threshold + 4):
                    if df['close'].iloc[i0 - _r_off] >= df['ANCHOR'].iloc[i0 - _r_off]:
                        state._reclaim_run += 1
                    else:
                        break

                # If only 1-2 reclaim bars, check for floor failure behind them
                if 1 <= state._reclaim_run <= 2:
                    _hist_below = 0
                    for _h_off in range(state._reclaim_run, state._reclaim_run + _ff_lookback):
                        _h_dist = df['ANCHOR'].iloc[i0 - _h_off] - df['close'].iloc[i0 - _h_off]
                        if _h_dist > grace:
                            _hist_below += 1
                        else:
                            break

                    if _hist_below >= _ff_threshold:
                        # Recent floor failure with insufficient reclaim — re-assert
                        state.is_floor_failure = True
                        state.is_reclaim = False
                        state.consec_below = _hist_below
                # _reclaim_run >= 3: floor failure fully resolved, no re-assertion

        # ======================================================================
        # METRICS PAYLOAD  [MANDATE: DOC 3 SEC 498 & DOC 8 SEC 466]
        # All values normalised to display currency (pence -> pounds for GBP).
        # ======================================================================

        state.floor_raw   = last['ANCHOR']
        floor_price = round(state.floor_raw / price_scaler, 2)
        hard_stop   = round(hard_stop_raw / price_scaler, 2)

        # Profile-specific derived metrics  [MANDATE: DOC 2 SEC 4.3]
        # [PE-26] Profit_Target_Synthetic for Profile B: Floor + 1.5 ATR.
        # A risk-calibrated intermediate profit objective for pullback entries.
        # Suppressed if price is already above it (target is behind current price).
        target_1_b  = round((state.floor_raw + (1.5 * state.atr_raw)) / price_scaler, 2) if p_code == "B" else None
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
            "EMA 8 (Convexity Protocol)"         if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else
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
            "VIOLATED -- RECLAIM ACTIVE (STATE AMBIGUOUS)"  if (state.is_reclaim and not (state._entry_trending or state._entry_resolving)) else
            "VIOLATED -- RECLAIM ACTIVE"                    if state.is_reclaim   else
            "VIOLATED -- AWAITING RECLAIM"                  if state.is_violated  else
            "TRENDING"                                      if state.is_trending  else
            "RESOLVING"                                     if state.is_resolving else
            "MID-RANGE (ADX <20)"                           if state.adx_t < 20 else
            "MID-RANGE (MA SQUEEZE)"                          if state.ma_squeeze else
            "TRENDING (ETF -- BASELINE FLOOR ONLY)"         if (is_etf and state.ma_stack_full and state.adx_t > 20 and not state.ma_squeeze) else
            "RESOLVING (ETF -- BASELINE FLOOR ONLY)"        if (is_etf and state.adx_t >= 20) else
            "AMBIGUOUS (DOWNTREND -- ADX MEASURING BEARISH MOMENTUM)"  if state._resolving_is_bearish else
            "AMBIGUOUS (MA STACK BROKEN)"                   if state.adx_t >= 25 else
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
        if round(atr_dist, 2) > 0 and (state.is_violated or state.is_floor_failure) and _live_bar_above_floor:
            metrics["ATR_Dist_Note"] = (
                f"LIVE BAR RECOVERY: current bar above floor ({round(last['close'] / price_scaler, 2)} > "
                f"{round(last['ANCHOR'] / price_scaler, 2)}) but floor "
                f"{'failure' if state.is_floor_failure else 'violation'} based on "
                f"{state.consec_below} completed bar(s) below. "
                f"Check Exit_Signal field for position management status."
            )
        # [BUG #39 FIX] ETF Profile B uses SMA_50 as proximity anchor (not EMA_21).
        # ETF Profile C uses SMA_200 (same as structural floor -- not EMA_21).
        # ETF cases must be evaluated BEFORE the generic p_code in ("B","C") branch
        # which previously caused ETF assets to display an incorrect anchor label.
        metrics["ATR_Dist_Anchor"]   = (
            "EMA_8"   if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else
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
        metrics["Anchor_Type"]       = "EMA_8" if (p_code == "B" and state.is_resolving and not state.is_trending and not is_etf) else "Standard"
        metrics["Anchor_Label"]      = anchor_label
        metrics["ADX"]               = round(state.adx_t, 2)
        metrics["DI_Plus"]           = round(state.di_plus, 2)
        metrics["DI_Minus"]          = round(state.di_minus, 2)
        metrics["Engine_State"]      = engine_state
        metrics["Conviction"]        = conviction_state
        metrics["Inst_Churn"]        = mod_d_state
        metrics["ADX_Accel"]         = adx_accel
        metrics["ADX_Accel_State"]   = adx_accel_state
        metrics["Vol_Confirm_Ratio"] = vol_confirm_ratio
        metrics["Vol_Confirm_State"] = vol_confirm_state
        metrics["Active_Modifiers"]  = ", ".join(active_mods) if active_mods else "None"
        resistance_display = round((df['high'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].max()) / price_scaler, 2)
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
            if state.is_floor_failure or (last['close'] < state.floor_raw):
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
        metrics["ATR"]               = round(state.atr_raw         / price_scaler, _atr_display_dp)
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
            risk_b   = last['close']  - state.floor_raw
            # [CONVEXITY] C-3 Expectancy Gate bypass (Redesign Proposal §6.2 / Execution Map §VI)
            # C-3 has open-ended reward. Computing R:R against a fixed resistance level
            # treats the breakout as a range-bound trade, which contradicts the C-3 thesis.
            # Profit_Target is written as INFORMATIONAL (see Profit_Target_Role field).
            # Reward_Risk is suppressed — operator uses Risk_Per_Unit instead.
            if _is_c3:
                if _resistance_suppressed or (state.is_floor_failure or (last['close'] < state.floor_raw)):
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
                if state.is_floor_failure or (last['close'] < state.floor_raw):
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
        if _is_c3 and state.is_resolving and not state.is_trending and p_code == "B":
            _ema8_risk = last['close'] - last['EMA_8']
            if not pd.isna(_ema8_risk) and state.atr_raw > 0:
                metrics["Risk_Per_Unit"] = round(_ema8_risk / state.atr_raw, 2)

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
            exit_b_conv  = bool(state.is_resolving and not state.is_trending and (last['close'] < last['EMA_8']))
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
        if state.is_floor_failure and exit_signal != "EXIT":
            exit_signal = "EXIT"
            metrics["Exit_Signal"] = "EXIT"
            # [PE-28] Append structural trigger to existing triggers list
            _existing_triggers = metrics.get("Exit_Triggers", [])
            if isinstance(_existing_triggers, str):
                _existing_triggers = []
            _existing_triggers.append("Floor_Failure_Override")
            metrics["Exit_Triggers"] = _existing_triggers
            metrics["Exit_Reason"] = (
                f"FLOOR FAILURE OVERRIDE: {state.consec_below} consecutive completed bars below floor. "
                f"Reclaim progress: {state._reclaim_run}/3 bars above floor. "
                f"3 consecutive closes above floor required to reset structural break."
            )
            metrics["Floor_Failure_Reclaim"] = f"{state._reclaim_run}/3"

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
        # [RFT-001 Phase 6C] Computation moved to _assemble_output (Layer 5).
        # Keys pre-populated here to preserve metrics dict field ordering.
        # _assemble_output overwrites with computed values.
        # ======================================================================
        metrics['Trend_Health_Score'] = None
        metrics['THS_Label']         = None
        metrics['THS_Floor_Buffer']  = None
        metrics['THS_Dir_Momentum']  = None
        metrics['THS_Trend_Age']     = None
        metrics['THS_Structure']     = None
        metrics['Trend_Age_Bars']    = None

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
        # [RFT-001 Phase 7 NOTE] ENG-001 stays at this position (before gates).
        # Option B (move to _assemble_output) was attempted but created a
        # behavioral delta: post-gate Profit_Target values changed
        # RN_Target_Proximity from None to "CLEAR" on several paths.
        # PE-7b and Bug #33 also stay upstream for the same ordering reason.
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

        # [RFT-001 Phase 4] Context data already fetched in _fetch_and_compute().
        # df_ctx unpacked from raw_metrics above. No IB call needed here.
        ctx_res, ctx_dur = cfg.ctx_resolution, cfg.ctx_duration

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

        # ==================================================================
        # [CEG-002] EARLY PROFIT TARGET EXTRACTION
        #
        # cons_high_raw is the profit target numerator for Capital R:R.
        # Previously computed inside the Profile A Expectancy pre-check,
        # which is unreachable on early-return paths. Extract here so
        # Capital_Reward_Risk can be computed before any gate fires.
        #
        # Profile A: 10-bar daily high from context chart, fallback to hourly.
        # Profile B: uses resistance_raw (already available), not cons_high_raw.
        # Profile C: no profit targets.
        # ==================================================================
        cons_high_raw = None
        _profit_target_source = None

        if p_code == "A":
            if df_ctx is not None and len(df_ctx) >= 11:
                cons_high_raw = df_ctx['high'].iloc[-11:-1].max()
                if cons_high_raw < last['close']:
                    cons_high_raw = resistance_raw
                    _profit_target_source = "HOURLY_RESISTANCE (price above daily range)"
                else:
                    _profit_target_source = "DAILY_CTX"
            else:
                cons_high_raw = df['high'].iloc[-12:-2].max()
                _profit_target_source = "FALLBACK_HOURLY (context data unavailable)"
            metrics["Cons_High"] = round(cons_high_raw / price_scaler, 2)
            metrics["Profit_Target_Source"] = _profit_target_source

        # ==================================================================
        # [CEG-002] EARLY CAPITAL R:R COMPUTATION
        #
        # Surfaces Capital_Reward_Risk and Capital_RR_Label on ALL paths,
        # including early-return HALTs where CEG-001 is unreachable.
        # CEG-001 gate logic is unchanged — it overwrites these values
        # when reached (Profile A gate, Profile B transparency).
        #
        # Suppression guards (per Operator design decisions):
        #   - Exit_Signal = EXIT: suppress (consistent with PE-7)
        #   - Price below floor (floor failure/violation): suppress (misleading)
        #   - Profile C: not applicable (no profit targets)
        #   - No positive reward or risk: null (structurally non-computable)
        # ==================================================================
        _early_capital_target = None
        if p_code == "A" and cons_high_raw is not None:
            _early_capital_target = cons_high_raw
        elif p_code == "B":
            _early_capital_target = resistance_raw

        _early_capital_risk = last['close'] - hard_stop_raw

        # Suppression guards
        _suppress_capital_rr = (
                exit_signal == "EXIT"
                or state.is_floor_failure
                or state.is_violated
                or _early_capital_target is None
                or _early_capital_target <= last['close']
                or _early_capital_risk <= 0
        )

        if _suppress_capital_rr:
            metrics["Capital_Reward_Risk"] = None
            metrics["Capital_RR_Label"] = None
        else:
            _early_crr = (_early_capital_target - last['close']) / _early_capital_risk
            metrics["Capital_Reward_Risk"] = round(_early_crr, 2)
            if _early_crr < 1.0:
                metrics["Capital_RR_Label"] = "INSUFFICIENT"
            elif _early_crr < 1.5:
                metrics["Capital_RR_Label"] = "NARROW"
            else:
                metrics["Capital_RR_Label"] = "HEALTHY"

        # ==================================================================
        # [PE-31] EARLY-RETURN DIAGNOSTIC GUARD
        #
        # Phase 1 writes Resistance_Note and Reward_Risk_Note with generic
        # defaults that assume Phase 4 will contextualise them. On any
        # early-return path (CRG-1, CRG-2, Floor Failure, MID-RANGE, etc.),
        # these strings are misleading or factually wrong.
        #
        # Save Phase 1 values to local variables and null them in metrics.
        # Phase 4 restore block will re-populate if the engine reaches it.
        # This covers ALL current and future early-return paths automatically.
        # ==================================================================
        _p1_resistance_note  = metrics.get("Resistance_Note")
        _p1_reward_risk_note = metrics.get("Reward_Risk_Note")
        metrics["Resistance_Note"]  = None
        metrics["Reward_Risk_Note"] = None

        # ======================================================================
        # EPX-001: ENTRY PROXIMITY SIGNAL — POST-VERDICT AUDIT
        # [Amendment EPX-001 v1.0]
        # [RFT-001 Phase 6A] _proximity_audit promoted to top-level function.
        # Build context dict for all proximity audit calls.
        # ======================================================================
        _prx_ctx = dict(
            state=state, mode=mode, p_code=p_code, is_etf=is_etf, last=last,
            prev_high=prev_high, resistance_raw=resistance_raw,
            ext_limit=ext_limit, atr_dist=atr_dist,
            window_count=window_count, window_limit=window_limit,
            cons_high_raw=cons_high_raw, hard_stop_raw=hard_stop_raw,
            price_scaler=price_scaler, prox_anchor=prox_anchor,
            df=df, structural_floor_raw=structural_floor_raw,
        )

        # ======================================================================
        # [RFT-001 Phase 6B] RESULT-COLLECTION PATTERN
        # Gate cascade uses result_status/result_diagnostic instead of early
        # returns. Gates evaluate sequentially; first failure is collected.
        # Control falls through to single return point at bottom.
        # ======================================================================
        result_status = None
        result_diagnostic = None

        # ======================================================================
        # GATE 1: CONTEXT REGIME  [CRG-1 Profile A + CRG-2 Profile B]
        # ======================================================================
        _result = _gate_context_regime(p_code, df_ctx, price_scaler, metrics)
        if _result is not None:
            result_status, result_diagnostic = _result

        # ======================================================================
        # GATE 2: LIQUIDITY  [Gate 0]
        # ======================================================================
        if result_status is None:
            _result = _gate_liquidity(adv_20, is_etf, _is_lse_etf, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # --- Initialize variables that are conditionally set by profile ---
        # risk_a and reward_a are computed only for Profile A in the Expectancy
        # Pre-Check below. Default to None so downstream gate calls
        # (_gate_expectancy, _gate_capital_expectancy) can safely receive them
        # for all profiles — the gates check p_code before accessing these.
        risk_a   = None
        reward_a = None

        # --- FLOOR VIOLATION PRE-CHECK ---
        # Must run BEFORE the Expectancy gate (which computes risk_a = price - VWAP
        # and fires a confusing "floor integrity failure" when price < VWAP).
        # Any broken-floor state is caught here with the correct diagnostic.
        # [R-1 FIX] Pre-check now uses Profile A's i0=-2 offset to evaluate the same
        # bar window as the main check. Previously used df.iloc[-1 - offset] which was
        # shifted by 1 bar for Profile A, causing potential disagreement on floor state.
        if result_status is None and state.atr_raw > 0:
            _precheck_i0 = cfg.iq  # [R-1] Match main check's i0
            floor_dist_pre = (df['close'].iloc[_precheck_i0] - df['ANCHOR'].iloc[_precheck_i0]) / state.atr_raw
            grace_pre = 0.15 * state.atr_raw
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
                result_status = "HALT"
                result_diagnostic = (
                        f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE{' RECOVERY' if _pre_reclaim > 0 else ''}: "
                        f"{consec_pre} consecutive bars below Floor. "
                        + (f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                           if _pre_reclaim > 0 else "Structural break.")
                )

            # [3-BAR RECLAIM MANDATE -- PRE-CHECK DEEP SCAN]
            # After 2 reclaim bars, the simple backward counter no longer detects
            # the floor failure (below-floor bars shifted out of lookback window).
            # Scan deeper to find recent failure behind the reclaim streak.
            if result_status is None and not is_floor_failure_pre and _precheck_current_above and not is_violated_pre:
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
                        # [EPX-001] Sync reclaim run for proximity audit
                        state._reclaim_run = _pre_reclaim
                        result_status = "HALT"
                        result_diagnostic = (
                            f"REJECT (reason: FLOOR FAILURE). FLOOR FAILURE RECOVERY: {_pre_hist} bars below Floor. "
                            f"Reclaim {_pre_reclaim}/3 -- need {3 - _pre_reclaim} more close(s) above floor."
                        )

            if result_status is None:
                if is_violated_pre and not is_reclaim_pre:
                    result_status = "HALT"
                    result_diagnostic = (f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: {consec_pre} bar(s) below Floor ({round(last['ANCHOR'] / price_scaler, 2)}). "
                                         f"Current bar has NOT reclaimed (Close {round(last['close'] / price_scaler, 2)} < Floor). "
                                         f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
                                         f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_pre}/3 bars).")
                elif floor_dist_pre < -0.15 and not is_violated_pre:
                    result_status = "HALT"
                    result_diagnostic = f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION: Price {abs(floor_dist_pre):.2f} ATR below Floor."

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

        if result_status is None and p_code == "A":
            # cons_high_raw, Cons_High, and Profit_Target_Source already
            # computed in the CEG-002 early extraction block.
            reward_a       = (cons_high_raw - last['close'])
            risk_a         = (last['close'] - last['ANCHOR'])   # Doc 2 P032: risk = distance to Structural Floor
            # Grace buffer: price within 0.15 ATR below floor is floor-hugging, not a breach.
            # Clamp risk_a to 0 in this zone (treated as floor-exact entry).
            _exp_grace = 0.15 * state.atr_raw if not pd.isna(state.atr_raw) and state.atr_raw > 0 else 0
            if pd.isna(risk_a):
                result_status = "HALT"
                result_diagnostic = "REJECT (reason: DATA INTEGRITY). Invalid Reward/Risk: risk_a is NaN."
            elif risk_a < -_exp_grace:
                # Price is materially below VWAP floor -- genuine integrity failure.
                result_status = "HALT"
                result_diagnostic = (f"WAIT (reason: FLOOR VIOLATION). FLOOR VIOLATION ACTIVE: price {round(last['close'] / price_scaler, 2)} is {abs(risk_a / state.atr_raw):.2f} ATR below floor ({round(last['ANCHOR'] / price_scaler, 2)}). Mandate: HARD WAIT.")
            else:
                if risk_a < 0:
                    # Within grace buffer -- treat as floor-exact entry (risk -> 0).
                    risk_a = 0
                if risk_a == 0:
                    # [PE-CAL-2] Price is exactly AT VWAP floor -- structurally optimal
                    # pullback entry, but floor-based R:R is undefined (denominator = 0).
                    # Substitute hard stop as risk denominator, same as floor-proximity.
                    if reward_a <= 0:
                        result_status = "HALT"
                        result_diagnostic = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: no upside reward from VWAP floor position."
                    else:
                        risk_a_hardstop = last['close'] - hard_stop_raw
                        if risk_a_hardstop <= 0:
                            result_status = "HALT"
                            result_diagnostic = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price at floor-exact entry."
                        else:
                            rr_hardstop = reward_a / risk_a_hardstop
                            if rr_hardstop < 2.0:
                                metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                                metrics["Reward_Risk_Note"] = (
                                    f"FLOOR_EXACT: price at VWAP; floor-based R:R undefined. "
                                    f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails 1:2 minimum."
                                )
                                result_status = "HALT"
                                result_diagnostic = (
                                    f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR EXACT): R:R {round(rr_hardstop, 2)}:1 < 2.0 "
                                    f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                                    f"Await wider reward ceiling or deeper pullback."
                                )
                            else:
                                metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                                metrics["Reward_Risk_Note"] = (
                                    f"FLOOR_EXACT: price at VWAP; R:R computed against hard stop "
                                    f"({round(hard_stop_raw / price_scaler, 2)}). Displayed R:R reflects actual capital at risk."
                                )
                                metrics["Profit_Target"]    = round(cons_high_raw / price_scaler, 2)
                elif risk_a < (0.20 * state.atr_raw):
                    # [PE-CAL-2] Risk denominator is near-zero (< 20% of ATR) -- the floor-based
                    # R:R is degenerate (small price movements swing R:R by 10+ points).
                    # Substitute the hard stop as the risk denominator.
                    risk_a_hardstop = last['close'] - hard_stop_raw
                    if risk_a_hardstop <= 0:
                        result_status = "HALT"
                        result_diagnostic = "REJECT (reason: DATA INTEGRITY). Invalid Expectancy: hard stop above current price in floor-proximity zone."
                    else:
                        rr_hardstop = reward_a / risk_a_hardstop
                        if rr_hardstop < 2.0:
                            metrics["Reward_Risk"]      = round(rr_hardstop, 2)
                            metrics["Reward_Risk_Note"] = (
                                f"FLOOR_PROXIMITY: floor-based risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                                f"substituted hard stop risk ({round(risk_a_hardstop / price_scaler, 2)}). "
                                f"Hard-stop R:R = {round(rr_hardstop, 2)}:1 -- fails 1:2 minimum."
                            )
                            result_status = "HALT"
                            result_diagnostic = (
                                f"REJECT (reason: EXPECTANCY FAILED). EXPECTANCY FAILED (FLOOR PROXIMITY): R:R {round(rr_hardstop, 2)}:1 < 2.0 "
                                f"(reward {round(reward_a / price_scaler, 2)} / hard-stop risk {round(risk_a_hardstop / price_scaler, 2)}). "
                                f"Floor-based R:R is degenerate (risk < 20% ATR). Await wider reward ceiling or deeper pullback."
                            )
                        else:
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
        # ======================================================================
        # PHASE 3: GATE EVALUATION  [MANDATE: DOC 2 SEC II, III, IV, VI, VII]
        # Gates 3-15 extracted per RFT-001 Phase 1.
        # ======================================================================

        # Gate 3 — Data Integrity (ATR NaN/0 check)
        if result_status is None:
            _result = _gate_data_integrity(state.atr_raw, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        floor_dist = (last['close'] - last['ANCHOR']) / state.atr_raw

        # Gate 4 — Floor Failure
        if result_status is None:
            _result = _gate_floor_failure(state.consec_below, state.is_floor_failure, p_code, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 5 — Floor Violation
        if result_status is None:
            _result = _gate_floor_violation(floor_dist, state.is_violated, p_code, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 6 — Floor Violation Active (no reclaim)
        if result_status is None:
            _result = _gate_floor_violation_active(state.is_violated, state.is_reclaim, state.consec_below, floor_price,
                                                   last['close'], price_scaler, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 7 — Volume Climax
        if result_status is None:
            _result = _gate_climax(df, p_code, state.is_reclaim, check_climax_history, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 8 — MID-RANGE (ADX < 20 / MA Squeeze)
        if result_status is None:
            _result = _gate_midrange(state.adx_t, state.ma_squeeze, atr_dist, ext_limit, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # ==================================================================
        # TIER 2 GATES: SIGNAL VALIDITY  [MANDATE: DOC 2 SEC V.2]
        # ==================================================================

        # Gate 9 — Directional Dominance
        if result_status is None:
            _result = _gate_directional(state.di_plus, state.di_minus, p_code, state.ema_stacked, state._entry_trending,
                                        state.ma_stack_full, floor_prox_pct, state.adx_t, state.adx_t1, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 10 — Modifier E Gap-Trap
        if result_status is None:
            _result = _gate_modifier_e(last['open'], prev_high, state.atr_raw, last['close'], metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 11 — Execution Window
        if result_status is None:
            _result = _gate_window(window_count, window_limit, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # ==================================================================
        # TIER 3 GATES: SAFETY CONSTRAINTS  [MANDATE: DOC 2 SEC V.3]
        # ==================================================================

        # Gate 12 — Extension
        if result_status is None:
            _result = _gate_extension(atr_dist, ext_limit, p_code, is_etf, state.is_trending, state.is_resolving,
                                      state._entry_trending, state._entry_resolving, last, resistance_raw,
                                      resistance_display, _resistance_suppressed, floor_prox_pct,
                                      adx_accel_state, adx_accel, vol_confirm_state, vol_confirm_ratio,
                                      exit_signal, structural_floor_raw, state.atr_raw, price_scaler,
                                      metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 13 — Floor Proximity (Profile C only)
        if result_status is None:
            _result = _gate_floor_proximity_c(p_code, last, floor_prox_pct, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 14 — Expectancy (Profile A)
        if result_status is None:
            _result = _gate_expectancy(p_code, risk_a, reward_a, cons_high_raw, last['close'],
                                       floor_price, price_scaler, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Gate 15 — Capital Expectancy (CEG-001)
        if result_status is None:
            _result = _gate_capital_expectancy(p_code, risk_a, cons_high_raw, last['close'],
                                               hard_stop_raw, resistance_raw, state.atr_raw,
                                               price_scaler, metrics)
            if _result is not None:
                result_status, result_diagnostic = _result

        # Recover _capital_rr and _reward_label from metrics (set by _gate_capital_expectancy)
        # — these locals are consumed by Phase 4 diagnostic strings.
        _capital_rr = metrics.get("Capital_Reward_Risk")
        _reward_label = metrics.get("Capital_RR_Label")

        # PHASE 4: TRIGGER IDENTIFICATION & CADENCE BINDING
        # [RFT-001 Phase 7] Extracted to _identify_trigger() per spec §III.6.
        result_status, result_diagnostic = _identify_trigger(
            state=state, cfg=cfg, p_code=p_code, is_etf=is_etf, metrics=metrics,
            result_status=result_status, result_diagnostic=result_diagnostic,
            last=last, df=df, resistance_raw=resistance_raw,
            resistance_display=resistance_display,
            floor_price=floor_price, hard_stop=hard_stop, chart_ref=chart_ref,
            conviction_state=conviction_state, price_scaler=price_scaler,
            _resistance_suppressed=_resistance_suppressed,
            _capital_rr=_capital_rr, _reward_label=_reward_label,
            _p1_resistance_note=_p1_resistance_note,
            _p1_reward_risk_note=_p1_reward_risk_note,
            profile=profile, clean_ticker=clean_ticker,
            adx_col=adx_col, dmp_col=dmp_col, dmn_col=dmn_col,
            chart_dir=chart_dir,
        )

        # ==================================================================
        # [RFT-001 Phase 6C] SINGLE RETURN POINT — Layer 5 Output Assembly
        # THS computation and proximity audit handled inside _assemble_output.
        # ==================================================================
        return _assemble_output(
            metrics, result_status, result_diagnostic, state, cfg,
            last, df, window_count, _is_c3, _prx_ctx
        )


    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", {}


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

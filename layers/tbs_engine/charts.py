import plotly.graph_objects as go
from plotly.subplots import make_subplots

__all__ = ['_build_primary_chart', '_build_context_chart', '_build_focus_chart']
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
                       adx_col, dmp_col, dmn_col, cfg=None):
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
    # PE-43: Use cfg.resistance_slice_start:end for all profiles.
    # All profiles now use the same 10-bar window via cfg (A: -11:-1, B: -11:-1, C: -11:-1).
    if cfg is not None:
        focus_df = df.iloc[cfg.resistance_slice_start:cfg.resistance_slice_end]
    else:
        # Defensive fallback (cfg not passed — legacy call paths)
        focus_df = df.iloc[-11:-1]
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

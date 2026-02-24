import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
# TBS PURITY ENGINE (Layer 2) v8.3
# Bug fixes: PE-1 (NYSE retry gated on USD currency)
#            PE-2 (Engine_State label: distinguish ADX<20 from MA Squeeze; PE-2b: ADX<20 takes priority when both true)
#            PE-3 (LSE ETFs: add VANG keyword + LSEETF exchange detection; override price_scaler to 1.0)
#            PE-4 (LSE ETF liquidity threshold: $5M instead of $50M -- market-maker backed, low on-exchange vol)
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio

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
        title=f"TBS v8.3 Primary View: {clean_ticker} [{profile}]",
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

    fig.update_layout(
        template="plotly_dark", height=700,
        title=f"TBS v8.3 Context View ({ctx_label}): {clean_ticker} [{profile}]",
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
    if len(df) < 11:
        raise ValueError("Insufficient bars for Focus Chart (requires >= 11).")
    focus_df  = df.iloc[-11:-1]   # 10 completed bars, no active bar
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
    fig.add_hline(
        y=cons_high / price_scaler,
        line=dict(color='orange', dash='dash', width=1.5),
        annotation_text=f"Cons. High: {cons_high / price_scaler:.2f}",
        annotation_position="top right", row=1, col=1
    )
    fig.add_hline(
        y=cons_low / price_scaler,
        line=dict(color='orange', dash='dot', width=1.5),
        annotation_text=f"Cons. Low: {cons_low / price_scaler:.2f}",
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
        title=f"TBS v8.3 Focus View (10-Bar Window): {clean_ticker} [{profile}]",
        xaxis_rangeslider_visible=False, showlegend=True
    )
    return fig


# ==============================================================================
# MAIN ENGINE
# ==============================================================================

def run_tbs_engine(ticker, profile="TREND", is_etf=False, mode="INFO",
                   exchange="SMART", currency="USD"):

    # --- [MANDATE: CONCURRENCY INTEGRITY] ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

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
        p_code    = p_mapping.get(profile.upper(), "B")
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
        p_code_early = {"SWING": "A", "TREND": "B", "WEALTH": "C",
                        "A": "A", "B": "B", "C": "C"}.get(profile.upper(), "B")
        min_bars_required = 30 if p_code_early == "A" else 220
        if len(df) < min_bars_required:
            return (
                "HALT",
                f"Insufficient historical data: {len(df)} bars retrieved "
                f"(requires >= {min_bars_required} for Profile {p_code_early}). "
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
        # p_code not yet assigned -- use early mapping
        for col in required_ma_cols.get(p_code_early, []):
            if col not in df.columns or df[col].isna().all():
                return (
                    "HALT",
                    f"Indicator computation failed: {col} is entirely NaN. "
                    f"Insufficient price history for this indicator on {clean_ticker}.",
                    metrics
                )

        # --- COLUMN IDENTIFICATION (dynamic -- never hardcode column names) ---
        adx_candidates = [c for c in df.columns if c.startswith('ADX') and 'DM' not in c]
        dmp_candidates = [c for c in df.columns if 'DMP' in c]
        dmn_candidates = [c for c in df.columns if 'DMN' in c]

        if not adx_candidates:
            return "HALT", "ADX column not found -- pandas_ta.adx() failed or insufficient data.", metrics
        if not dmp_candidates or not dmn_candidates:
            return "HALT", "Directional Movement columns (DI+/DI-) not found.", metrics

        adx_col = adx_candidates[0]
        dmp_col = dmp_candidates[0]
        dmn_col = dmn_candidates[0]

        adx_t,  adx_t1, adx_t2 = df[adx_col].iloc[-1], df[adx_col].iloc[-2], df[adx_col].iloc[-3]
        di_plus  = df[dmp_col].iloc[-1]
        di_minus = df[dmn_col].iloc[-1]

        # --- [MANDATE: DOC 2 SEC 4.2] MA SQUEEZE ---
        df['MA_Dist'] = abs(df['EMA_8'] - df['EMA_21'])
        df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])
        ma_squeeze    = bool(
            df['Squeeze'].iloc[-1] and df['Squeeze'].iloc[-2] and df['Squeeze'].iloc[-3]
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
                last['EMA_21'] > last['SMA_50']
        )
        is_trending = ma_stack_full and (adx_t > 20) and not ma_squeeze

        # EMA stacked: EMA8 > EMA21 -- used solely for Profile A DI exemption
        ema_stacked = last['EMA_8'] > last['EMA_21']

        # ETF Logic Lock -- overrides both state flags per Doc 6
        if is_etf:
            is_resolving = False
            is_trending  = False

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
        if _resolving_is_bearish:
            is_resolving = False

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
                return "HALT", f"Unknown profile code for ETF routing: {p_code}", metrics

        if p_code == "A":
            df.ta.vwap(append=True)
            vwap_cols = [c for c in df.columns if 'VWAP' in c]
            if not vwap_cols:
                return "HALT", "VWAP column not found -- pandas_ta.vwap() failed or insufficient data.", metrics
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
        atr_val = atr_raw  # backward-compatible alias (safe; prevents NameError if any legacy references remain)
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
            # [MANDATE: DOC 2 SEC VIII] Profile C anchor is always EMA_21 (Weekly).
            # Must NOT inherit the Profile B RESOLVING->EMA_8 branch.
            prox_anchor = last['EMA_21']
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
        #   Profile B TRENDING     : 1.0 ATR  -- EMA 21 anchor, accommodates MA lag in live trend
        #   Profile C (WEALTH)     : 0.5 ATR  -- EMA 21 Weekly, floor proximity audit is primary
        #   ETF (any profile)      : 0.5 ATR  -- conservative baseline, no state differentiation
        if p_code == "A":
            ext_limit = 1.5
        elif p_code == "C":
            ext_limit = 0.5
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

        df['Is_Pullback'] = (
                (df['close'] <= (df['ANCHOR'] + (0.5 * df['ATRr_14']))) &
                (df['close'] >= df['ANCHOR'])
        )

        if p_code == "A":
            df.loc[df.index[-1], 'Is_Breakout'] = False
            df.loc[df.index[-1], 'Is_Pullback'] = False

        # Window limits per profile  [MANDATE: DOC 2 SEC III]
        # A=4 hourly bars (VWAP resets daily -- natural staleness protection)
        # B=5 daily bars  (SMA 50 pullbacks develop over 3-7 days)
        # C=2 weekly bars (2 weeks is sufficient for position trade)
        window_limit  = 4 if p_code == "A" else (5 if p_code == "B" else 2)
        window_tail   = window_limit + 10  # lookback buffer -- always larger than the limit

        recent_series = (df['Is_Breakout'] | df['Is_Pullback'])
        recent_events = (recent_series.iloc[:-1].tail(window_tail) if p_code == "A" else recent_series.tail(window_tail)).astype(bool).to_list()
        window_count  = recent_events[::-1].index(True) if any(recent_events) else 99  # 99 = sentinel: no valid window found

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

        # Grace buffer: a bar must close more than 0.15 ATR below the floor to count
        # as a "below" bar. This prevents micro-wicks and hairline breaches from
        # triggering violated/failure states on stocks hugging their floor.
        grace = 0.15 * float(df['ATRr_14'].iloc[i0]) if not pd.isna(df['ATRr_14'].iloc[i0]) else 0

        if current_above_floor:
            # Current bar reclaimed. Count consecutive below-floor bars among
            # PRIOR bars (k=2 is the bar before current, k=3 is two bars ago...).
            consec_below = 0
            for offset in range(1, 5):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    consec_below += 1
                else:
                    break  # Streak broken -- stop counting
            is_violated     = False                       # Current bar is healthy
            is_reclaim      = (1 <= consec_below <= 3)   # 1-3 prior bars below = Reclaim
            is_floor_failure = (consec_below >= 4)        # 4+ prior bars below = structural failure
        else:
            # Current bar is below floor. Count the current streak including it.
            consec_below = 0
            for offset in range(0, 5):
                bar_dist = df['ANCHOR'].iloc[i0 - offset] - df['close'].iloc[i0 - offset]
                if bar_dist > grace:
                    consec_below += 1
                else:
                    break
            is_violated      = (1 <= consec_below <= 3)  # Waiting for Reclaim
            is_reclaim       = False                      # Current bar not above floor
            is_floor_failure = (consec_below >= 4)        # Structural failure

        # ======================================================================
        # METRICS PAYLOAD  [MANDATE: DOC 3 SEC 498 & DOC 8 SEC 466]
        # All values normalised to display currency (pence -> pounds for GBP).
        # ======================================================================

        floor_raw   = last['ANCHOR']
        floor_price = round(floor_raw / price_scaler, 2)
        hard_stop   = round(hard_stop_raw / price_scaler, 2)

        # Profile-specific derived metrics  [MANDATE: DOC 2 SEC 4.3]
        # Target 1 for Profile B: +1.5 ATR from the Structural Floor.
        # Suppressed if price is already above Target 1 -- field would be misleading
        # to the Operator (target is behind current price, not ahead of it).
        target_1_b  = round((floor_raw + (1.5 * atr_raw)) / price_scaler, 2) if p_code == "B" else None
        if target_1_b is not None and target_1_b <= actual_price:
            target_1_b = None
            metrics["Target_1_Note"] = "SUPPRESSED: price already above Target 1 -- await pullback to floor"

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
            "VIOLATED -- RECLAIM ACTIVE (STATE AMBIGUOUS)"  if (is_reclaim and not (is_trending or is_resolving)) else
            "VIOLATED -- RECLAIM ACTIVE"                    if is_reclaim   else
            "VIOLATED -- AWAITING RECLAIM"                  if is_violated  else
            "TRENDING"                                      if is_trending  else
            "RESOLVING"                                     if is_resolving else
            "MID-RANGE (ADX <20)"                           if adx_t < 20 else
            "MID-RANGE (MA SQUEEZE)"                          if ma_squeeze else
            "TRENDING (ETF -- BASELINE FLOOR ONLY)"         if (is_etf and ma_stack_full and adx_t >= 25) else
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
            metrics["Stop_Value"]    = hard_stop   # legacy key for Orchestrator
        else:
            metrics["Hard_Stop"]     = None
            metrics["Stop_Value"]    = None
            metrics["Hard_Stop_Note"] = "SUPPRESSED: stop above current price -- floor already broken, Exit_Signal active"
        metrics["ADV_20"]            = float(adv_20)
        metrics["ATR_Dist"]          = round(atr_dist, 2)
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
                f"{round(last['ANCHOR'] / price_scaler, 2)}) but floor failure based on "
                f"{consec_below} completed bar(s) below -- Exit_Signal remains active until "
                f"a clean confirmed close above floor is established."
            )
        # [BUG #39 FIX] ETF Profile B uses SMA_50 as proximity anchor (not EMA_21).
        # ETF Profile C uses SMA_200 (same as structural floor -- not EMA_21).
        # ETF cases must be evaluated BEFORE the generic p_code in ("B","C") branch
        # which previously caused ETF assets to display an incorrect anchor label.
        metrics["ATR_Dist_Anchor"]   = (
            "EMA_8"   if (p_code == "B" and is_resolving and not is_trending and not is_etf) else
            "SMA_50"  if (is_etf and p_code == "B") else   # ETF Profile B: SMA_50 anchor (immutable)
            "SMA_200" if (is_etf and p_code == "C") else   # ETF Profile C: SMA_200 anchor (same as floor)
            "EMA_21"  if p_code in ("B", "C") else         # [MANDATE: DOC 2 SEC VIII] Profile C = EMA_21
            "VWAP"    if p_code == "A" else
            "SMA_200"
        )
        metrics["window_count"]      = int(window_count)
        metrics["Anchor_Type"]       = "EMA_8" if (p_code == "B" and is_resolving and not is_trending and not is_etf) else "Standard"
        metrics["Anchor_Label"]      = anchor_label
        metrics["ADX"]               = round(adx_t, 2)
        metrics["DI_Plus"]           = round(di_plus, 2)
        metrics["DI_Minus"]          = round(di_minus, 2)
        metrics["Engine_State"]      = engine_state
        metrics["Conviction"]        = conviction_state
        metrics["Inst_Churn"]        = mod_d_state
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
        metrics["SMA_200"]           = round(last['SMA_200'] / price_scaler, 2)
        metrics["SMA_50"]            = round(last['SMA_50']  / price_scaler, 2)

        # Target_1 written after Exit Conditions block -- see line below exit_signal assignment.

        # Profile B Reward/Risk  [MANDATE: DOC 2 SEC 4.3 / audit parity with Profile A]
        # Reward = Resistance (10-bar consolidation high) - Price
        # Risk   = Price - Structural Floor (SMA_50)
        # Mirrors Profile A convention: risk measured to structural floor, not Hard_Stop.
        if p_code == "B":
            reward_b = resistance_raw - last['close']
            risk_b   = last['close']  - floor_raw
            # [BUG #42 FIX -- secondary] When resistance is suppressed (price above
            # the 10-bar ceiling), RR_Target_Price and Reward_Risk must also be nulled.
            # Computing R:R against a suppressed resistance produces a contradictory
            # payload: the note declares no reward ceiling while the number implies one.
            if _resistance_suppressed:
                metrics["RR_Target_Price"]  = None
                metrics["Reward_Risk"]      = None
                metrics["Reward_Risk_Note"] = (
                    f"UNDEFINED: price ({actual_price}) above resistance ceiling ({resistance_display}) -- "
                    f"no reward target available. Await pullback to floor ({floor_price}) before re-evaluating."
                )
            elif pd.isna(risk_b) or risk_b < 0:
                metrics["RR_Target_Price"]  = round(resistance_raw / price_scaler, 2)
                metrics["Reward_Risk"]      = None
                metrics["Reward_Risk_Note"] = "UNDEFINED: price below structural floor"
            elif risk_b == 0:
                metrics["RR_Target_Price"]  = round(resistance_raw / price_scaler, 2)
                metrics["Reward_Risk"]      = 9999.0
                metrics["Reward_Risk_Note"] = "FLOOR_EXACT: price at SMA_50; risk denominator = 0; R:R treated as maximal"
            else:
                metrics["RR_Target_Price"]  = round(resistance_raw / price_scaler, 2)
                metrics["Reward_Risk"]      = round(reward_b / risk_b, 2)

        if floor_prox_pct is not None:
            metrics["Floor_Prox_Pct"] = float(floor_prox_pct)     # Profile C only

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

        # All Exit_Signal values cast to native Python bool.
        # pandas comparisons return numpy.bool_ which json.dumps cannot serialize.
        if p_code == "A":
            est_hourly_low_raw = float(df['low'].iloc[-12:-2].min())
            exit_a_low    = bool(last['close'] < est_hourly_low_raw)
            exit_a_vwap   = bool(consec_below >= 3)   # [MANDATE: DOC 2 SEC X] 3 consecutive hourly closes below VWAP
            exit_signal   = exit_a_low or exit_a_vwap
            metrics["Exit_Signal"]     = exit_signal
            metrics["Exit_Reason"]     = (
                "Close below established Hourly Low" if exit_a_low else
                f"VWAP Violation ({consec_below} consecutive bar(s) below floor)" if exit_a_vwap
                else "None"
            )
        elif p_code == "B":
            exit_b_std   = bool(last['close'] < last['SMA_50'])
            exit_b_conv  = bool(is_resolving and not is_trending and (last['close'] < last['EMA_8']))
            exit_signal  = exit_b_std or exit_b_conv
            metrics["Exit_Signal"]     = exit_signal
            metrics["Exit_Reason"]     = (
                "Close below EMA 8 (Convexity active)" if exit_b_conv else
                "Close below 50-SMA" if exit_b_std
                else "None"
            )
        elif p_code == "C":
            exit_signal  = bool(last['close'] < last['SMA_200'])
            metrics["Exit_Signal"]     = exit_signal
            metrics["Exit_Reason"]     = "Close below 200-SMA" if exit_signal else "None"

        # [BUG #33 FIX -- RELOCATED] Write Target_1 here, after exit_signal is assigned
        # for all three profiles. The early Target_1 block (price > target suppression)
        # ran before exit_signal existed, causing UnboundLocalError on Profile B/C runs.
        # Both suppression conditions are now evaluated in correct execution order:
        #   1. Price > Target_1     -- handled at computation site (line ~855)
        #   2. Exit_Signal active   -- handled here, post exit_signal assignment
        if target_1_b is not None and exit_signal:
            target_1_b = None
            metrics["Target_1_Note"] = "SUPPRESSED: Exit_Signal active -- floor broken, no entry context"
        if target_1_b is not None:
            metrics["Target_1"] = target_1_b          # Profile B only

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

        # Gate 0 -- Liquidity fast-path  [Doc 2 Sec.II / Doc 8 Sec.II-IV]
        # Must fire BEFORE the floor pre-check so illiquid tickers never surface
        # floor-failure diagnostics (which would mask the true rejection reason).
        # [PE-4] LSE ETFs trade lower on-exchange volume but are backed by market
        # makers arbitraging against the underlying index. $5M threshold (same as
        # equities) filters genuinely illiquid products while admitting established
        # Vanguard/iShares UCITS ETFs. US ETFs retain the $50M threshold.
        _adv_limit_early = 5_000_000 if _is_lse_etf else (50_000_000 if is_etf else 5_000_000)
        if not pd.isna(adv_20) and adv_20 < _adv_limit_early:
            return "HALT", f"Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${_adv_limit_early/1e6:.0f}M)", metrics

        # --- FLOOR VIOLATION PRE-CHECK ---
        # Must run BEFORE the Expectancy gate (which computes risk_a = price - VWAP
        # and fires a confusing "floor integrity failure" when price < VWAP).
        # Any broken-floor state is caught here with the correct diagnostic.
        atr_raw_precheck = float(last['ATRr_14']) if not pd.isna(last['ATRr_14']) else 0
        if atr_raw_precheck > 0:
            floor_dist_pre = (last['close'] - last['ANCHOR']) / atr_raw_precheck
            grace_pre = 0.15 * atr_raw_precheck
            consec_pre = 0
            for offset in range(1, 5):
                bar_dist = df.iloc[-1 - offset]['ANCHOR'] - df.iloc[-1 - offset]['close']
                if bar_dist > grace_pre:
                    consec_pre += 1
                else:
                    break
            is_floor_failure_pre = consec_pre >= 4
            is_violated_pre      = 1 <= consec_pre <= 3
            is_reclaim_pre       = is_violated_pre and (last['close'] >= last['ANCHOR'])
            if is_floor_failure_pre:
                return "HALT", f"FLOOR FAILURE: {consec_pre} consecutive bars below Floor. Structural break.", metrics
            if is_violated_pre and not is_reclaim_pre:
                return (
                    "HALT",
                    f"FLOOR VIOLATION ACTIVE: {consec_pre} bar(s) below Floor ({round(last['ANCHOR'] / (100.0 if currency == 'GBP' else 1.0), 2)}). "
                    f"Current bar has NOT reclaimed (Close {round(last['close'] / (100.0 if currency == 'GBP' else 1.0), 2)} < Floor). "
                    f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
                    f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_pre}/3 bars).",
                    metrics
                )
            if floor_dist_pre < -0.15 and not is_violated_pre:
                return "HALT", f"FLOOR VIOLATION: Price {abs(floor_dist_pre):.2f} ATR below Floor.", metrics

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
                    metrics["Cons_High_Source"] = "HOURLY_RESISTANCE (price above daily range)"
                else:
                    metrics["Cons_High_Source"] = "DAILY_CTX"
            else:
                # Fallback to hourly if context data unavailable -- conservative
                cons_high_raw = df['high'].iloc[-12:-2].max()
                metrics["Cons_High_Source"] = "FALLBACK_HOURLY (context data unavailable)"
            reward_a       = (cons_high_raw - last['close'])
            risk_a         = (last['close'] - last['ANCHOR'])   # Doc 2 P032: risk = distance to Structural Floor
            metrics["Cons_High"]   = round(cons_high_raw / price_scaler, 2)
            # Grace buffer: price within 0.15 ATR below floor is floor-hugging, not a breach.
            # Clamp risk_a to 0 in this zone (treated as floor-exact entry).
            _exp_grace = 0.15 * atr_raw if not pd.isna(atr_raw) and atr_raw > 0 else 0
            if pd.isna(risk_a):
                return "HALT", "Invalid Reward/Risk: risk_a is NaN.", metrics
            if risk_a < -_exp_grace:
                # Price is materially below VWAP floor -- genuine integrity failure.
                return "HALT", f"FLOOR VIOLATION ACTIVE: price {round(last['close'] / price_scaler, 2)} is {abs(risk_a / atr_raw):.2f} ATR below floor ({round(last['ANCHOR'] / price_scaler, 2)}). Mandate: HARD WAIT.", metrics
            if risk_a < 0:
                # Within grace buffer -- treat as floor-exact entry (risk -> 0).
                risk_a = 0
            if risk_a == 0:
                # Price is exactly AT VWAP floor -- structurally optimal pullback entry.
                # R:R is undefined by the formula (denominator = 0, reward/risk -> inf).
                # Treat as maximal R:R: gate passes, sentinel recorded for audit trail.
                if reward_a <= 0:
                    return "HALT", "Invalid Expectancy: no upside reward from VWAP floor position.", metrics
                metrics["Reward_Risk"]      = 9999.0
                metrics["Reward_Risk_Note"] = "FLOOR_EXACT: price at VWAP; risk denominator = 0; R:R treated as maximal"
                metrics["RR_Target_Price"]  = round(cons_high_raw / price_scaler, 2)
            elif risk_a < (0.20 * atr_raw):
                # Risk denominator is near-zero (< 20% of ATR) -- R:R is mathematically
                # valid but display-unstable: sub-cent raw precision differences swing
                # the output by 10+ points. Cap at sentinel and flag for operator.
                metrics["Reward_Risk"]      = 9999.0
                metrics["Reward_Risk_Note"] = (
                    f"FLOOR_PROXIMITY: risk ({round(risk_a / price_scaler, 3)}) < 20% ATR -- "
                    f"denominator near-zero, R:R unstable. Floor-exact entry conditions apply."
                )
                metrics["RR_Target_Price"]  = round(cons_high_raw / price_scaler, 2)
            else:
                metrics["Reward_Risk"]      = round(reward_a / risk_a, 2)
                metrics["RR_Target_Price"]  = round(cons_high_raw / price_scaler, 2)

        # ======================================================================
        # PHASE 3: GATE EVALUATION  [MANDATE: DOC 2 SEC II, III, IV, VI, VII]
        # ======================================================================

        # Gate 1 -- Floor Integrity  [Doc 2 Sec 4.1]
        # Structural failure (4+ bars below) = immediate HALT.
        # VIOLATED (1-3 bars below) routes to Reclaim protocol -- checked in Phase 4.
        # A small grace buffer (-0.15 ATR) allows intrabar wicks below the floor.
        if pd.isna(atr_raw) or atr_raw == 0:
            return "HALT", "Invalid ATR for proximity math (ATR is NaN or 0).", metrics
        floor_dist = (last['close'] - last['ANCHOR']) / atr_raw
        if is_floor_failure:
            return "HALT", (f"FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break. (evaluated on last completed bar)" if p_code == "A" else f"FLOOR FAILURE: {consec_below} consecutive bars below Floor. Structural break."), metrics
        if floor_dist < -0.15 and not is_violated:
            return "HALT", (f"FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor. (evaluated on last completed bar)" if p_code == "A" else f"FLOOR VIOLATION: Price {abs(floor_dist):.2f} ATR below Floor."), metrics

        # Gate 1.5 -- VIOLATED state with no current-bar reclaim
        # When is_violated=True but the current bar is still below the floor,
        # no downstream gate produces a meaningful output. Fire here immediately
        # rather than letting Phase 1.5 Expectancy or Phase 4 AMBIGUOUS catch it
        # with a misleading diagnostic.
        if is_violated and not is_reclaim:
            return (
                "HALT",
                f"FLOOR VIOLATION ACTIVE: {consec_below} bar(s) below Floor ({floor_price}). "
                f"Current bar has NOT reclaimed (Close {round(last['close'] / price_scaler, 2)} < Floor {floor_price}). "
                f"Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above {floor_price}. "
                f"Note: Exit_Signal activates after 3 consecutive closes below floor ({consec_below}/3 bars).",
                metrics
            )

        # Gate 2 -- Liquidity  [Doc 2 Sec.II / Doc 8 Sec.II-IV]
        adv_limit = 5_000_000 if _is_lse_etf else (50_000_000 if is_etf else 5_000_000)
        if pd.isna(adv_20):
            return "HALT", "Liquidity Failed: ADV_20 is NaN (missing volume data).", metrics
        if adv_20 < adv_limit:
            return "HALT", f"Liquidity Failed ({'ETF' if is_etf else 'EQUITY'}): ${adv_20/1e6:.1f}M (Req >${adv_limit/1e6:.0f}M)", metrics

        # Gate 3 -- Volume Climax  [Doc 2 Sec.II / Doc 6 Sec.3.6]
        climax_df = df.iloc[:-1] if p_code == "A" else df
        if pd.isna(climax_df['vol_sma_9'].iloc[-1]):
            return "HALT", "Climax check failed: Volume SMA9 is NaN (insufficient volume history).", metrics
        climax, ago = check_climax_history(climax_df)
        if climax and ago is None:
            ago = 0
        if p_code == "A" and climax:
            ago += 1
        if climax:
            if is_reclaim:
                # Reclaim voided: cannot re-enter during the 3-bar climax window
                return "HALT", f"CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago.", metrics
            return "HALT", f"CLIMAX BLOCK: Institutional selling {ago} bars ago.", metrics

        # Gate 4 -- MID-RANGE Hard Wait  [Doc 2 Sec 4.2]
        # Must fire BEFORE Extension: extension is meaningless in a non-directional
        # regime. If ADX < 20, the asset has no trend to be extended from.
        if adx_t < 20:
            return "HALT", f"MID-RANGE BLOCK: ADX ({adx_t:.2f}) < 20. HARD WAIT.", metrics
        if ma_squeeze:
            return "HALT", "MID-RANGE BLOCK: EMA 8/21 Squeeze 3+ bars. HARD WAIT.", metrics

        # Gate 5 -- Extension  [Doc 2 Sec VIII]
        # ext_limit is computed upstream (state and profile dependent).
        # Only evaluated once a directional regime (ADX > 20) is confirmed.
        if atr_dist > ext_limit and not (p_code == "B" and not is_etf and not (is_trending or is_resolving)):
            # Gate 5.5 -- Profile C Floor Proximity Audit  [Doc 2 Sec 4.3]
            # Wealth entries are only authorized when within 8% of the Weekly 200-SMA.
            if p_code == "C":
                if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
                    return "HALT", "Invalid SMA_200 for Floor Proximity Audit.", metrics
                floor_prox_pct = abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100
                if floor_prox_pct > 8.0:
                    return "HALT", f"FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct:.2f}% > 8.0%.", metrics

            return "HALT", f"EXTENDED: {atr_dist:.2f} ATR above limit ({ext_limit})", metrics

        # Gate 5.5 -- Profile C Floor Proximity Audit  [Doc 2 Sec 4.3]
        # Wealth entries are only authorized when within 8% of the Weekly 200-SMA.
        if p_code == "C":
            if pd.isna(last['SMA_200']) or last['SMA_200'] == 0:
                return "HALT", "Invalid SMA_200 for Floor Proximity Audit.", metrics
            floor_prox_pct_gate = abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100
            if floor_prox_pct_gate > 8.0:
                return "HALT", f"FLOOR PROXIMITY FAILED (Profile C): {floor_prox_pct_gate:.2f}% > 8.0%.", metrics


        # Gate 6 -- Directional Dominance  [Doc 2 Sec VI]
        if pd.isna(di_plus) or pd.isna(di_minus):
            return "HALT", "Directional Dominance failed: DI values are NaN.", metrics
        if di_minus > di_plus and (p_code == "A" or is_etf or is_trending or is_resolving):
            if p_code == "A" and ema_stacked:
                pass  # Profile A exemption: EMA 8 > EMA 21 stack intact
            elif p_code == "B" and is_trending and ma_stack_full:
                pass  # Profile B TRENDING exemption: full MA stack overrides momentary
                # -DI dominance during pullback corrective phase  [DOC 2 SEC VI]
            else:
                return "HALT", f"DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f})", metrics

        # Gate 7 -- Modifier E Gap-Trap  [Doc 2 Sec VII]
        if (last['open'] > (prev_high + (0.5 * atr_raw))) and (last['close'] < last['open']):
            return "HALT", "MODIFIER E BLOCK: Gap-Trap. Immediate HALT.", metrics

        # Gate 8 -- Execution Window  [Doc 2 Sec III]
        # window_limit: A=4 hourly, B=5 daily, C=2 weekly
        if window_count > window_limit:
            wc_label = "NONE FOUND (sentinel)" if window_count == 99 else str(window_count)
            return "HALT", f"WINDOW EXPIRED: Window {wc_label} (Requires 0-{window_limit}). PLANNING ONLY.", metrics

        # Gate 8.5 -- Profile A Expectancy Gate  [Doc 2 Sec 4.3 / P032 / P038]
        # Enforced here so it applies to ALL PASS paths: Pullback, Breakout, Reclaim.
        # No Profile A trade may bypass the 1:2 reward/risk requirement.
        if p_code == "A":
            if risk_a < 0:
                return "HALT", "Invalid expectancy math: price is below VWAP floor.", metrics
            elif risk_a == 0:
                pass  # Floor-exact entry: R:R is structurally maximal. Gate passes.
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
                return "HALT", f"EXPECTANCY GATE FAILED (Profile A): {reason}", metrics

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
        at_pullback_zone = (
                (last['close'] >= last['ANCHOR']) and
                (last['close'] <= (last['ANCHOR'] + (0.5 * atr_raw)))
        )

        # [MANDATE: DOC 2 SEC VI.2] Convex Support: Price > EMA 8 required at breakout
        # resistance_raw pre-computed before Phase 1.5 -- no re-definition needed here.
        at_breakout = (
                (last['close'] > resistance_raw) and
                (last['close'] > last['EMA_8'])
        )

        # ---- PHASE 4: SINGLE if/elif/elif/else CHAIN ----
        # All four paths are mutually exclusive. The first matching condition
        # sets verdict/diag and falls through to Phase 4B (Focus chart).
        # Only HALT paths use inline return. PASS paths never inline-return.
        #
        # Priority order:
        #   1. RECLAIM   -- VIOLATED state + current bar above floor
        #   2. TRENDING  -- ADX > 25 + full MA stack
        #   3. RESOLVING -- ADX > 20 + 3-bar slope
        #   4. AMBIGUOUS -- ADX 20-25, no confirmed state

        # ---- PRIORITY 1: RECLAIM PROTOCOL  [Doc 2 Sec VI.3] ----
        if is_reclaim:
            # State quality gate: reclaim is only a valid re-entry signal if the
            # underlying directional state is confirmed (TRENDING or RESOLVING).
            # An AMBIGUOUS reclaim means price has recovered the floor but the trend
            # regime is not active -- this is a structural bounce, not a qualified entry.
            if not (is_trending or is_resolving):
                return (
                    "HALT",
                    f"RECLAIM DETECTED but state AMBIGUOUS: ADX {adx_t:.1f} -- MA stack incomplete "
                    f"and no confirmed 3-bar ADX slope. Floor reclaimed ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                    f"but directional regime not active. Mandate: HARD WAIT. "
                    f"Monitor for state upgrade (RESOLVING or TRENDING) before re-entry.",
                    metrics
                )
            verdict = "PASS"
            diag    = (
                f"PROVISIONAL PASS (RECLAIM | BAR CLOSE ONLY). "
                f"Current bar closed above Floor ({round(last['close'] / price_scaler, 2)} > {floor_price}) "
                f"after {consec_below} prior bar(s) below Floor. "
                f"ADX: {adx_t:.1f}. "
                f"Entry: execute at THIS bar's close. "
                f"If close missed: next bar must ALSO close above {floor_price} before entry is valid. "
                f"Stop: {hard_stop}. {chart_ref}"
            )

        # ---- PRIORITY 2: TRENDING STATE -- Standard/Pullback Protocol  [Doc 2 Sec VI.1] ----
        elif is_trending:
            if at_pullback_zone:
                verdict = "PASS"
                diag    = (
                    f"PROVISIONAL PASS (PULLBACK | TRENDING | BAR CLOSE ONLY). "
                    f"Price {round(last['close'] / price_scaler, 2)} within pullback zone "
                    f"[{floor_price} -- {round((last['ANCHOR'] + 0.5 * atr_raw) / price_scaler, 2)}]. "
                    f"ADX: {adx_t:.1f}. "
                    f"Entry: execute at THIS bar's close. "
                    f"If close missed: next bar must ALSO close within pullback zone before entry is valid. "
                    f"Stop: {hard_stop}. {chart_ref}"
                )
            else:
                return (
                    "HALT",
                    f"TRENDING (ADX {adx_t:.1f}) -- price not in pullback zone. "
                    f"Mandate: WAIT for Floor Test at {floor_price}.",
                    metrics
                )

        # ---- PRIORITY 3: RESOLVING STATE -- Convexity/Breakout Protocol  [Doc 2 Sec VI.2] ----
        # [MANDATE: DOC 2 SEC VI] Profile A Exemption: "The Convexity Protocol is architecturally
        # incompatible with mean-reversion entries." Profile A is a VWAP pullback profile only.
        # A RESOLVING Profile A asset must wait for price to return to the VWAP floor.
        elif is_resolving:
            if p_code == "A":
                return (
                    "HALT",
                    f"CONVEXITY PROTOCOL BLOCKED (Profile A): "
                    f"Profile A is a mean-reversion profile -- VWAP pullback entry only. "
                    f"Mandate: WAIT for price to return to VWAP floor ({floor_price}). "
                    f"ADX: {adx_t:.1f} (RESOLVING state active).",
                    metrics
                )
            if at_breakout:
                verdict = "PASS"
                sizing  = "Full Unit" if conviction_state.startswith("HIGH") else "50% Unit (Low Conviction)"
                diag    = (
                    f"TECHNICAL PASS (BREAKOUT | RESOLVING | INTRADAY). "
                    f"Price {round(last['close'] / price_scaler, 2)} closed above resistance {metrics['Resistance']}. "
                    f"ADX: {adx_t:.1f}. Sizing: {sizing}. "
                    f"Entry: INTRADAY permitted -- may enter while breakout bar is still forming. "
                    f"Convex Support: price must remain above EMA 8 ({metrics['EMA_8']}). "
                    f"Stop: {hard_stop}. {chart_ref}"
                )
            else:
                reason = (
                    "No breakout above resistance"  if not df['Is_Breakout'].iloc[-1]
                    else "Convex Support failed: Price below EMA 8"
                )
                return (
                    "HALT",
                    f"RESOLVING (ADX {adx_t:.1f}) -- {reason} at {metrics['Resistance']}. "
                    f"Mandate: WAIT for Consolidation Range violation.",
                    metrics
                )

        # ---- PRIORITY 4: AMBIGUOUS (ADX 20-25, MA stack incomplete) ----
        else:
            return (
                "HALT",
                f"ENGINE STATE AMBIGUOUS: ADX {adx_t:.1f} > 20 but TRENDING not confirmed "
                f"(MA stack incomplete or ADX < 25). Mandate: HARD WAIT.",
                metrics
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

        return verdict, diag, metrics

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", {}
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",  required=True)
    parser.add_argument("--profile", default="TREND")
    parser.add_argument("--mode",    default="INFO")
    parser.add_argument("--etf",     action="store_true")
    args = parser.parse_args()

    status, diag, metrics = run_tbs_engine(
        args.ticker, args.profile, args.etf, args.mode
    )
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))

import json
import os
import sys
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
from ib_insync import IB, Contract, util, Stock

# --- [MANDATE: DOC 2 SEC 235] CLIMAX LOCKOUT HELPER ---
def check_climax_history(df):
    """Verifies the mandatory 3-bar block following a Volume Climax."""
    for i in range(1, 4):
        try:
            vol = df['volume'].iloc[-i]
            sma9 = df['vol_sma_9'].iloc[-i]
            is_neg = df['close'].iloc[-i] < df['open'].iloc[-i]
            if vol > (2 * sma9) and is_neg:
                return True, i
        except (IndexError, KeyError):
            continue
    return False, 0

def run_tbs_engine(ticker, profile="TREND", is_etf=False, mode="INFO", exchange="SMART", currency="USD"):
    # --- [MANDATE: CONCURRENCY INTEGRITY] ---
    # Ensure a valid event loop exists for the AnyIO worker thread
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Generate unique ID to prevent IBKR "Already Connected" collisions
    unique_client_id = 25 + (os.getpid() % 100)
    # --- END CONCURRENCY PATCH ---

    port = 4002 if mode.upper() == "INFO" else 4001

    # DEFINITION: This instantiates the IB class into the variable 'ib'
    ib = IB()

    metrics = {} # [MANDATE: DOC 8 SEC 39] Initialize for SSoT Handshake

    # --- [MANDATE: DOC 8 SEC 23] DYNAMIC ROUTING & NORMALIZATION ---
    clean_ticker = ticker.upper()
    p_exchange = ""
    routing_map = {
        '.L': {'exchange': 'SMART', 'currency': 'GBP', 'primary': 'LSE'},
        '.TO': {'exchange': 'SMART', 'currency': 'CAD', 'primary': 'TSE'},
        '.DE': {'exchange': 'IBIS', 'currency': 'EUR', 'primary': 'IBIS'},
        '.AS': {'exchange': 'AEB', 'currency': 'EUR', 'primary': 'AEB'},
        '.PA': {'exchange': 'SBF', 'currency': 'EUR', 'primary': 'SBF'}
    }

    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exchange'], route['currency'], route['primary']
            break

    # Automated override for VWRP if provided without suffix
    if clean_ticker == "VWRP" and currency == "USD":
        exchange, currency, p_exchange = "SMART", "GBP", "LSE"

    try:
        # 1. Get the absolute path of the directory containing this script (scripts/)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # 2. Go up one level to target the project root
        project_root = os.path.dirname(script_dir)
        # 3. Explicitly define the charts directory at the root
        chart_dir = os.path.join(project_root, "charts")
        if not os.path.exists(chart_dir): os.makedirs(chart_dir)

        # CONNECT: Using the unique_client_id generated above
        ib.connect('127.0.0.1', port, clientId=unique_client_id)

        # [MANDATE: DOC 8 SEC 23] Contract with PrimaryExchange Disambiguation
        # Moved forward to allow metadata identification fail-safe
        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)

        # --- [MANDATE: DOC 8 SEC 467] INDEPENDENT ASSET IDENTIFICATION ---
        # Fail-safe: Verify asset type via IBKR metadata to enforce correct Liquidity Gate
        details = ib.reqContractDetails(contract)
        if details:
            meta = details[0].longName.upper()
            # Authoritative keywords from Document 8 [cite: 469]
            etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS', 'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']
            if any(key in meta for key in etf_keywords):
                is_etf = True

        # 1. PROFILE & TIMEFRAME MAPPING
        p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
        p_code = p_mapping.get(profile.upper(), "B")
        tf_map = {"A": ("1 hour", "3 M"), "B": ("1 day", "2 Y"), "C": ("1 week", "10 Y")}
        res, dur = tf_map[p_code]

        bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True)
        if not bars: return "ERROR", f"No data retrieved for {clean_ticker}", {}

        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        # --- [MANDATE: TIMEFRAME NORMALIZATION] ---
        # Determine session length to scale metrics properly for the 20-Day Gate
        if "hour" in res:
            bars_per_day = 8.5 if currency == "GBP" else 7
        else:
            bars_per_day = 1

        sma_20_length = int(20 * bars_per_day)

        # 2. INDICATOR STACK
        df.ta.ema(length=8, append=True); df.ta.ema(length=21, append=True)
        df.ta.sma(length=50, append=True); df.ta.sma(length=200, append=True)
        df.ta.adx(length=14, append=True); df.ta.atr(length=14, append=True)
        df.ta.sma(close=df['volume'], length=9, append=True, col_names=('vol_sma_9',))
        df.ta.sma(close=df['volume'], length=sma_20_length, append=True, col_names=('vol_sma_20',))

        # --- [MANDATE: DOC 2 SEC 296 & DOC 6 SEC 196] ANCHOR & ETF LOGIC LOCK ---
        adx_col = [c for c in df.columns if 'ADX' in c][0]
        dmp_col = [c for c in df.columns if 'DMP' in c][0]
        dmn_col = [c for c in df.columns if 'DMN' in c][0]

        adx_t, adx_t1, adx_t2 = df[adx_col].iloc[-1], df[adx_col].iloc[-2], df[adx_col].iloc[-3]
        di_plus = df[dmp_col].iloc[-1]
        di_minus = df[dmn_col].iloc[-1]

        # --- [MANDATE: DOC 2 SEC 256] MA SQUEEZE CALCULATION ---
        df['MA_Dist'] = abs(df['EMA_8'] - df['EMA_21'])
        df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])
        ma_squeeze = df['Squeeze'].iloc[-1] and df['Squeeze'].iloc[-2] and df['Squeeze'].iloc[-3]

        # --- [MANDATE: DOC 2 SEC 296 & DOC 6 SEC 196] RESOLVING STATE LOCK ---
        # Resolving = ADX > 20 with 3-bar positive slope [Doc 2].
        # ADDED: Resolving is strictly VOID if an active MA Squeeze exists.
        is_resolving = (adx_t > 20) and (adx_t > adx_t1 > adx_t2) and not ma_squeeze
        ema_stacked = df['EMA_8'].iloc[-1] > df['EMA_21'].iloc[-1]

        # --- [MANDATE: DOC 2 SEC 245-247] STRUCTURAL FLOOR MAPPING ---
        if is_etf:
            is_resolving = False
            df['ANCHOR'] = df['SMA_50'] if p_code == "B" else df['SMA_200']
        else:
            if p_code == "A":
                # [MANDATE: DOC 2 SEC 246] VWAP is the sole Structural Floor for Profile A
                df.ta.vwap(append=True)
                vwap_col = [c for c in df.columns if 'VWAP' in c][0]
                df['ANCHOR'] = df[vwap_col]
            elif p_code == "B":
                df['ANCHOR'] = df['EMA_8'] if is_resolving else df['SMA_50']
            elif p_code == "C":
                df['ANCHOR'] = df['SMA_200']

        # --- [MANDATE: DOC 2 SEC 324 & DOC 8 SEC 465] UNIT NORMALIZATION & HARD STOP ---
        last = df.iloc[-1]
        price_scaler = 100.0 if currency == "GBP" else 1.0
        actual_price = last['close'] / price_scaler

        # --- [MANDATE: DOC 8 SEC 465] HARD STOP & FLOOR SEPARATION ---
        # Structural Floor = The technical level (EMA/SMA/VWAP)
        # Hard Stop = The mechanical exit level (Floor - 1.5 ATR)
        atr_val = last['ATRr_14']
        structural_floor_raw = last['ANCHOR']

        # [MANDATE: DOC 2 SEC 194] Mechanical Matrix Enforcement
        if p_code == "A":
            # Profile A Stop: min(Hourly Low, VWAP) - (1.5 * ATR)
            hard_stop_raw = min(last['low'], structural_floor_raw) - (1.5 * atr_val)
        else:
            hard_stop_raw = structural_floor_raw - (1.5 * atr_val)

        # Populate metrics for Orchestrator Order Execution
        metrics["Price"] = round(actual_price, 2)
        metrics["Structural_Floor"] = round(structural_floor_raw / price_scaler, 2)
        metrics["Hard_Stop"] = round(hard_stop_raw / price_scaler, 2)
        # Retaining Stop_Value for legacy compatibility in the dashboard
        metrics["Stop_Value"] = metrics["Hard_Stop"]

        # Raw Hourly Calculations
        adv_20_hourly = (df['vol_sma_20'].iloc[-1] * actual_price)

        # [MANDATE: DOC 2 SEC 272] Decouple Proximity Anchor from Structural Floor
        if is_etf:
            prox_anchor = last['SMA_50'] if p_code == "B" else last['SMA_200']
        else:
            # Enforces the Convexity Exemption (Anchor shifts to EMA 8 if resolving)
            prox_anchor = last['EMA_8'] if is_resolving else last['EMA_21']

        atr_dist = (last['close'] - prox_anchor) / last['ATRr_14']

        # --- [MANDATE: DOC 2 SEC 70] FINAL ADV CALCULATION ---
        # Scales the average bar volume to a daily notional value
        adv_20 = adv_20_hourly * bars_per_day


        # --- [MANDATE: DOC 2 SEC 287-290 & 321-327] MORPHOLOGY & CONVICTION ---
        total_range = last['high'] - last['low']
        real_body = abs(last['close'] - last['open'])

        # Breakout Conviction (Forces 50% cut if Range < 1.2 ATR)
        if total_range < (1.2 * last['ATRr_14']):
            conviction_state = "LOW (Range < 1.2 ATR)"
        else:
            conviction_state = "HIGH (Range > 1.2 ATR)"

        # Modifier D: Institutional Churn
        # Trigger: Extended (>0.5 ATR from EMA 21) AND Vol > 1.5x SMA 9 AND Body < 25% Range
        dist_ema21 = (last['close'] - last['EMA_21']) / last['ATRr_14']
        mod_d_vol = last['volume'] > (1.5 * df['vol_sma_9'].iloc[-1])
        mod_d_body = real_body < (0.25 * total_range) if total_range > 0 else False

        if (dist_ema21 > 0.5) and mod_d_vol and mod_d_body:
            mod_d_state = "ACTIVE (Inst. Churn)"
        else:
            mod_d_state = "CLEAR (No Churn)"

        # --- [MANDATE: DOC 2 SEC 302-320] POSITIVE MORPHOLOGY (MODIFIERS A, B, C) ---
        prev_high, prev_low = df['high'].iloc[-2], df['low'].iloc[-2]

        # Modifier A: Structural Rejection
        mod_a = (total_range > (0.5 * last['ATRr_14'])) and (last['low'] < last['ANCHOR']) and \
                (last['close'] > last['ANCHOR']) and \
                ((min(last['open'], last['close']) - last['low']) > (0.6 * total_range))

        # Modifier B: Momentum Ignition
        mod_b = (last['close'] > prev_high) and (real_body > (0.7 * total_range)) and \
                (last['volume'] > df['vol_sma_9'].iloc[-1])

        # Modifier C: Compression Bar
        mod_c = (last['high'] < prev_high) and (last['low'] > prev_low) and \
                (abs(last['close'] - last['ANCHOR']) <= (0.5 * last['ATRr_14']))

        active_mods = []
        if mod_a: active_mods.append("A (Rejection)")
        if mod_b: active_mods.append("B (Ignition)")
        if mod_c: active_mods.append("C (Compression)")
        metrics["Active_Modifiers"] = ", ".join(active_mods) if active_mods else "None"


        # --- [MANDATE: DOC 2 SEC 236-242] EXECUTION WINDOW BINDING ---

        # --- [MANDATE: DOC 2 SEC 236-242] CONSOLIDATION & WINDOW BINDING ---
        # 1. Identify the 10-Bar Focus Window (strictly completed bars)
        df['Prev_10_High'] = df['high'].shift(1).rolling(window=10).max()
        df['Prev_10_Low'] = df['low'].shift(1).rolling(window=10).min()

        # 2. Breakout Definition: Close strictly outside the preceding 10-bar range
        df['Is_Breakout'] = (df['close'] > df['Prev_10_High'])

        # 3. [MANDATE: DOC 2 SEC 241] PULLBACK RESET
        # A Pullback resets the window ONLY if it tests the anchor and holds with positive morphology
        # logic: Close within 0.5 ATR of Anchor AND (Close > Open OR Long Lower Tail)
        lower_tail = (df[['open', 'close']].min(axis=1) - df['low'])
        df['Is_Pullback'] = (df['close'] <= (df['ANCHOR'] + (0.5 * df['ATRr_14']))) & \
                            (df['close'] >= df['ANCHOR']) & \
                            ((df['close'] > df['open']) | (lower_tail > (0.5 * (df['high'] - df['low']))))

        # Scan the last 15 bars to find the most recent breakout OR pullback event
        recent_events = (df['Is_Breakout'] | df['Is_Pullback']).tail(15)

        if recent_events.any():
            # Reversing the array maps the current bar to 0, 1 bar ago to 1, etc.
            window_count = int(recent_events.iloc[::-1].argmax())
        else:
            # If no valid structural event occurred recently, the setup is severely stale
            window_count = 99

        # --- [MANDATE: DOC 3 SEC 498 & DOC 8 SEC 466] SSoT METRICS PAYLOAD ---
        # Normalizing metrics for the Governor's Risk and Sizing math
        metrics["ADV_20"] = adv_20
        metrics["ATR_Dist"] = round(atr_dist, 2)
        metrics["Price"] = round(actual_price, 2)
        metrics["window_count"] = window_count

        # Stop_Value must be the Hard Stop Price, NOT the Anchor [Doc 2 Sec 433]
        metrics["Stop_Value"] = round(hard_stop_raw / price_scaler, 2)
        metrics["Structural_Floor"] = round(last['ANCHOR'] / price_scaler, 2)

        if is_resolving and not is_etf:
            anchor_label = "EMA 8 (Convexity Protocol)"
        else:
            if p_code == "A": anchor_label = "VWAP (Baseline Floor)"
            elif p_code == "B": anchor_label = "50-SMA (Baseline Floor)"
            else: anchor_label = "200-SMA (Baseline Floor)"

        metrics["Anchor_Type"] = "EMA_8" if is_resolving and not is_etf else "Standard"
        metrics["ADX"] = round(adx_t, 2)
        metrics["Conviction"] = conviction_state
        metrics["Inst_Churn"] = mod_d_state  # [MANDATE: DOC 2] Updated to Technical Reference Name

        # --- [MANDATE: DOC 2 SEC 335] 10-BAR CONSOLIDATION MATH ---
        # Resistance defined as the Maximum High of the last 10 completed bars
        metrics["Resistance"] = round(df['high'].iloc[-11:-1].max() / price_scaler, 2)
        metrics["EMA_8"] = round(last['EMA_8'] / price_scaler, 2)
        metrics["ATR"] = round(last['ATRr_14'] / price_scaler, 2)
        metrics["SMA_200"] = round(last['SMA_200'] / price_scaler, 2)

        # Explicitly expose VWAP for the Swing Profile
        if p_code == "A":
            vwap_col = [c for c in df.columns if 'VWAP' in c][0]
            metrics["VWAP"] = round(last[vwap_col] / price_scaler, 2)


        # --- [TBS DEBUG: DATA INTEGRITY AUDIT] ---
        if mode == "INFO":
            # (Keep your debug prints commented out here to prevent JSON corruption)
            pass

        # --- PHASE 2: CHART RENDERING (THE TRIPLE-VIEW MANDATE) ---
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
            row_heights=[0.5, 0.25, 0.25],
            specs=[[{"secondary_y": False}], [{"secondary_y": False}], [{"secondary_y": True}]]
        )

        # Subplot 1: Price Action
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)

        # DYNAMIC PROFILE CHARTING
        if p_code == "A": # SWING (Hourly)
            vwap_col = [c for c in df.columns if 'VWAP' in c][0]
            fig.add_trace(go.Scatter(x=df.index, y=df[vwap_col], name="VWAP", line=dict(color='fuchsia', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_8'], name="EMA 8", line=dict(color='cyan', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name="EMA 21", line=dict(color='yellow', width=2)), row=1, col=1)

        elif p_code == "C": # WEALTH (Weekly)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_8'], name="8-Wk EMA", line=dict(color='cyan', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name="21-Wk EMA", line=dict(color='yellow', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name="50-Wk SMA", line=dict(color='red', dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], name="200-Wk SMA", line=dict(color='white', dash='dash')), row=1, col=1)

        else: # TREND (Daily Default)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_8'], name="EMA 8", line=dict(color='cyan', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], name="EMA 21", line=dict(color='yellow', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name="SMA 50", line=dict(color='red', dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], name="SMA 200", line=dict(color='white', dash='dash')), row=1, col=1)

        # Subplot 2: Volume & Volume SMA
        vol_colors = ['#00FF00' if df['close'].iloc[i] >= df['open'].iloc[i] else '#FF0000' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], name="Volume", marker_color=vol_colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['vol_sma_9'], name="Vol SMA 9", line=dict(color='orange')), row=2, col=1)

        # Subplot 3: ADX & ATR
        fig.add_trace(go.Scatter(x=df.index, y=df['ADX_14'], name="ADX 14", line=dict(color='purple')), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['ATRr_14'], name="ATR 14", line=dict(color='gray')), row=3, col=1, secondary_y=True)

        chart_filename = f"{clean_ticker}_triple_view.png"
        chart_path = os.path.join(chart_dir, chart_filename)
        # Added the Profile to the Chart Title for clarity
        fig.update_layout(template="plotly_dark", height=1000, title=f"TBS v8.2 Engine: {clean_ticker} [{profile}]", xaxis_rangeslider_visible=False)
        fig.write_image(chart_path)


        # --- PHASE 3: EVALUATE GATES AND EXECUTE HALTS ---

        # 1. FLOOR INTEGRITY / TREND ALIGNMENT [Doc 2 Sec 248-249]
        # Must measure against the Structural Floor (ANCHOR), NOT the Proximity Anchor
        floor_dist = (last['close'] - last['ANCHOR']) / last['ATRr_14']
        buffer_limit = -0.15
        if floor_dist < buffer_limit:
            return "HALT", f"FLOOR VIOLATION: Price is {abs(floor_dist):.2f} ATR below Structural Floor.", metrics

        # 2. LIQUIDITY FLOOR (Normalized Daily) [Doc 8 Sec 39]
        # $50M for ETFs / $5M for Equities
        adv_limit = 50000000 if is_etf else 5000000
        if adv_20 < adv_limit:
            return "HALT", f"Liquidity Failed: ${adv_20/1e6:.1f}M (Req >${adv_limit/1e6:.1f}M)", metrics

        # 3. VOLUME CLIMAX (Institutional Selling Filter) [Doc 2 SEC 314 & DOC 6 SEC 391]
        climax, ago = check_climax_history(df)

        # [MANDATE: DOC 2 SEC 393] CLIMAX PRECEDENCE CLAUSE
        # Check if a Reclaim (Close above floor after being below) is firing
        is_reclaim = (df['close'].iloc[-2] < df['ANCHOR'].iloc[-2]) and (df['close'].iloc[-1] > df['ANCHOR'].iloc[-1])

        if climax:
            if is_reclaim:
                # Reclaim triggers are explicitly VOID if within the 3-bar Climax window
                return "HALT", f"CLIMAX PRECEDENCE: Reclaim voided by Climax {ago} bars ago.", metrics
            return "HALT", f"CLIMAX BLOCK: Institutional selling {ago} bars ago.", metrics

        # 4. EXTENSION GATE (Greed Filter) [Doc 6 Sec 196]
        # Max 1.5 ATR for SWING / 0.5 ATR for TREND
        ext_limit = 1.5 if p_code == "A" else 0.5
        if atr_dist > ext_limit:
            return "HALT", f"EXTENDED: {atr_dist:.2f} ATR is above Limit ({ext_limit})", metrics

        # 5. RANGE STATE (The Engine State) [Doc 2 Sec 256]
        # Mandates a HARD WAIT if ADX < 20 OR if MAs are squeezed
        if adx_t < 20:
            return "HALT", f"MID-RANGE BLOCK: ADX ({adx_t:.2f}) is < 20. Mandate: HARD WAIT.", metrics
        if ma_squeeze:
            return "HALT", "MID-RANGE BLOCK: EMA 8 / EMA 21 Squeeze detected for 3+ bars. Mandate: HARD WAIT.", metrics

        # 6. DIRECTIONAL DOMINANCE (The Universal Preamble) [Doc 2 Sec 276 & 279]
        # Confirms buyer control (+DI > -DI). Profile A is conditionally exempt if EMAs are stacked.
        if di_minus > di_plus:
            if p_code == "A" and ema_stacked:
                pass  # Granted conditional exemption (Profile A with Stacked EMAs)
            else:
                return "HALT", f"DIRECTIONAL BLOCK: -DI ({di_minus:.2f}) > +DI ({di_plus:.2f})", metrics

        # 7. MODIFIER E (THE GAP-TRAP BLOCK) [Doc 2 Sec 328-332]
        prev_high = df['high'].iloc[-2]
        curr_open = df['open'].iloc[-1]
        curr_close = df['close'].iloc[-1]
        atr_14 = df['ATRr_14'].iloc[-1]

        if curr_open > (prev_high + (0.5 * atr_14)) and curr_close < curr_open:
            return "HALT", "MODIFIER E BLOCK: Gap-Trap detected. Immediate HALT.", metrics

        # 8. EXECUTION WINDOW BINDING [Doc 2 Sec 236-242]
        if window_count > 2:
            return "HALT", f"WINDOW EXPIRED: Trade is in Window {window_count} (Requires 0-2). Mandate: PLANNING ONLY.", metrics

        # --- [MANDATE: DOC 2 SEC 373-394] CADENCE & FLOOR VERIFICATION ---
        # Deterministic identification of the active trigger type
        is_active_pullback = df['Is_Pullback'].iloc[-1]
        floor_price = round(last['ANCHOR'] / price_scaler, 2)
        hard_stop = metrics["Stop_Value"]

        if is_active_pullback:
            # Standard Protocol (Pullback) requires confirmation of the close
            return "PASS", f"PROVISIONAL PASS (PULLBACK). Mandate: BAR CLOSE > {floor_price}. Stop: {hard_stop}. Chart: {chart_path}", metrics
        else:
            # Convexity Protocol (Breakout) authorizes immediate execution [cite: 386]
            return "PASS", f"TECHNICAL PASS (BREAKOUT). Mandate: INTRADAY ENTRY. Stop: {hard_stop}. Chart: {chart_path}", metrics
    except Exception as e:
        return "ERROR", str(e), {}
    finally:
        if ib.isConnected(): ib.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND")
    parser.add_argument("--mode", default="INFO")
    parser.add_argument("--etf", action="store_true")
    args = parser.parse_args()

    status, diag, metrics = run_tbs_engine(args.ticker, args.profile, args.etf, args.mode)
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))
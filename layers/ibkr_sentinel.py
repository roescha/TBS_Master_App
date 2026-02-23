import json
import asyncio
import os

from ib_insync import IB, Contract, util


def run_tbs_sentinel(ib_connection=None, port=4002):
    # --- START: CRITICAL CONCURRENCY PATCH ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Generate unique ID to prevent IBKR clientId collisions
    unique_client_id = 10 + (os.getpid() % 100)
    # --- END CONCURRENCY PATCH ---

    ib = ib_connection if ib_connection else IB()
    if not ib.isConnected():
        try:
            # Use unique_client_id instead of the hardcoded 10
            ib.connect('127.0.0.1', port, clientId=unique_client_id)
        except Exception as e:
            return "ERROR", "HALT", str(e)

    try:
        # Standard Systemic Proxies [cite: 106, 112]
        spy = Contract(symbol='SPY', secType='STK', exchange='SMART', currency='USD')
        tnx = Contract(symbol='TNX', secType='IND', exchange='CBOE', currency='USD')
        vix = Contract(symbol='VIX', secType='IND', exchange='CBOE', currency='USD')

        # Historical Data Request [cite: 107]
        spy_bars = ib.reqHistoricalData(spy, '', '6 M', '1 day', 'TRADES', True)
        tnx_bars = ib.reqHistoricalData(tnx, '', '6 M', '1 day', 'TRADES', True)
        vix_bars = ib.reqHistoricalData(vix, '', '1 M', '1 day', 'TRADES', True)

        df_spy = util.df(spy_bars)
        df_tnx = util.df(tnx_bars)
        df_vix = util.df(vix_bars)

        # SPY & TNX Indicator Stack
        df_spy.ta.sma(length=50, append=True)
        df_spy.ta.atr(length=14, append=True)
        df_tnx.ta.sma(length=10, append=True)
        df_tnx.ta.sma(length=50, append=True)
        df_tnx.ta.atr(length=14, append=True)

        # --- [MANDATE: DOC 5 SEC 2.3] VOLATILITY SHOCK & HIGH-WATER MANDATE ---
        # 1. Detect Volatility Shock (>25% session increase in SPY ATR) [cite: 260]
        atr_prev = df_spy['ATRr_14'].iloc[-2]
        atr_curr = df_spy['ATRr_14'].iloc[-1]
        is_vol_shock = (atr_curr > (1.25 * atr_prev))

        # 2. Calculate Running Intraday True Range [cite: 262]
        intraday_high = df_spy['high'].iloc[-1]
        intraday_low = df_spy['low'].iloc[-1]
        prev_close = df_spy['close'].iloc[-2]
        running_true_range = max(
            (intraday_high - intraday_low),
            abs(intraday_high - prev_close),
            abs(intraday_low - prev_close)
        )

        # --- [MANDATE: DOC 5 SEC 2.1 & 2.2] SUSTAINMENT CALCULATIONS ---
        # Yield Acceleration: TNX > 1.2 * ATR + 10-SMA
        y_accel = df_tnx['close'] > (df_tnx['SMA_10'] + (1.2 * df_tnx['ATRr_14']))
        # Volatility Expansion: VIX >= 25 OR SPY ATR > 1.5 * SMA 50
        v_exp = (df_vix['close'] >= 25.0) | (df_spy['ATRr_14'] > (1.5 * df_spy['SMA_50']))

        # High Risk Cascade requires 2-day sustainment
        is_high_risk = y_accel.iloc[-1] and y_accel.iloc[-2] and v_exp.iloc[-1] and v_exp.iloc[-2]

        # --- [MANDATE: DOC 5 SEC 2.2] STORM WATCH (Instantaneous Trigger) ---
        # VIX >= 25 activates the 50% Sizing Reduction on the FIRST daily close
        storm_watch = float(df_vix['close'].iloc[-1]) >= 25.0


        # --- [MANDATE: DOC 5 SEC 1.1] AMBIGUITY & REGIME IDENTIFICATION ---
        def get_bar_regime(idx):
            p = df_spy['close'].iloc[idx]
            s = df_spy['SMA_50'].iloc[idx]
            t_p = df_tnx['close'].iloc[idx]
            t_s = df_tnx['SMA_50'].iloc[idx]

            # [MANDATE: DOC 5 SEC 2.3 & 271] Deterministic 0.1 ATR Noise Floor
            # Use Running Intraday True Range if currently in a Volatility Shock [cite: 261, 271]
            if idx == -1 and is_vol_shock:
                buffer = 0.1 * running_true_range
            else:
                buffer = 0.1 * df_spy['ATRr_14'].iloc[idx]

            if is_high_risk: return "HIGH RISK (Black)"

            # [MANDATE: DOC 5 SEC 153] Ambiguity Clause: deterministic "Maybe" is a FAIL
            if abs(p - s) <= buffer: return "AMBIGUOUS"

            if p > s and t_p < t_s: return "BULLISH (Blue)"
            if p > s and t_p > t_s: return "DEFENSIVE (Yellow)"
            if p < s and t_p > t_s: return "RESTRICTED (Red)"
            if p < s and t_p < t_s: return "SHOCK (Grey)"
            return "UNKNOWN"

        # --- [MANDATE: DOC 5 SEC 131-134] SCALED CONFIRMATION MANDATE ---
        # Profile B (Trend) requires 3 Consecutive Daily Closes
        regime_history = [get_bar_regime(-3), get_bar_regime(-2), get_bar_regime(-1)]
        cur_regime = regime_history[-1]

        # Verify confirmed separation from Noise Floor and consistency
        is_confirmed = all(r == cur_regime for r in regime_history) and cur_regime != "AMBIGUOUS"

        if not is_confirmed:
            regime, verdict, reason = "AMBIGUOUS", "HALT", "Signal within 0.1 ATR Buffer or lacks 3-bar confirmation."
        else:
            regime = cur_regime
            if regime in ["BULLISH (Blue)", "DEFENSIVE (Yellow)"]: verdict = "PASS"
            elif regime in ["HIGH RISK (Black)", "SHOCK (Grey)"]: verdict = "FORCE HARVEST"
            else: verdict = "HALT" # Default for Restricted (Red) or Ambiguous
            reason = "Regime Mathematically Confirmed."

        # Final Dashboard Output
        v_close = float(df_vix['close'].iloc[-1])
        output = {"regime": regime, "verdict": verdict, "reason": reason, "vix": v_close}
        print(json.dumps(output, indent=4))
        # Return signature updated to include the Storm Watch flag
        return regime, verdict, reason, storm_watch

    except Exception as e:
        return "ERROR", "HALT", str(e)
    finally:
        if not ib_connection: ib.disconnect()

if __name__ == "__main__":
    run_tbs_sentinel()
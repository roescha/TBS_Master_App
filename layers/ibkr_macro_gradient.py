import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock, Index
import pandas as pd
import asyncio

# TBS MACRO GRADIENT (Step 1) v8.3.1
# Standalone pre-gate for the 8-Step Pipeline [DOC 5 SEC II / DOC 7 STEP 1]
#
# Full Sec II coverage:
#   1. SPY vs 50-SMA with 0.1 ATR Ambiguity Buffer + Scaled Confirmation [Sec II, II-A]
#   2. TNX vs 50-SMA for 4-tier regime classification [Sec II]
#   3. Yield Acceleration (TNX Sustainment Protocol) [Sec 2.1]
#   4. Storm Watch (VIX >= 25 instant defense) [Sec 2.2]
#   5. Volatility Expansion (HIGH RISK cascade) [Sec 2.2]
#   6. ATR Lag Dampener (Volatility Shock Protocol) [Sec 2.3]
#
# 4-Tier Regime Matrix [Doc 5 Sec II]:
#   GREEN  (Bullish)          : SPY > 50-SMA, TNX < 50-SMA
#   YELLOW (Defensive)        : SPY > 50-SMA, TNX > 50-SMA  -> 50% posture reduction
#   RED    (Restricted)       : SPY < 50-SMA, TNX > 50-SMA  -> HARD HALT + FORCE HARVEST weak
#   GREY   (Shock/Deflation)  : SPY < 50-SMA, TNX < 50-SMA  -> operationally = RED
#   BLACK  (High Risk)        : Yield Acceleration + Volatility Expansion -> overrides all
#
# Anchor Invariance [Doc 5 Sec II-A, P35]:
#   SMA 50 and ATR 14 are ALWAYS computed on DAILY bars regardless of profile.
#   Only the confirmation bar resolution changes per profile.


# ==============================================================================
# HELPER: Compute ATR series on a DataFrame
# ==============================================================================

def compute_atr(df, period=14):
    """Compute ATR using simple rolling mean of True Range."""
    df = df.copy()
    df['prev_close'] = df['close'].shift(1)
    df['TR'] = df.apply(
        lambda r: max(
            r['high'] - r['low'],
            abs(r['high'] - r['prev_close']) if pd.notna(r['prev_close']) else r['high'] - r['low'],
            abs(r['low'] - r['prev_close']) if pd.notna(r['prev_close']) else r['high'] - r['low']
        ), axis=1
    )
    df[f'ATR_{period}'] = df['TR'].rolling(period).mean()
    return df


# ==============================================================================
# HELPER: Count consecutive closes below/above a threshold
# ==============================================================================

def count_consecutive_below(df, threshold):
    """Count consecutive bars closing below threshold, from most recent backwards."""
    count = 0
    for i in range(len(df) - 1, -1, -1):
        if float(df.iloc[i]['close']) < threshold:
            count += 1
        else:
            break
    return count


def count_consecutive_above(df, threshold):
    """Count consecutive bars closing above threshold, from most recent backwards."""
    count = 0
    for i in range(len(df) - 1, -1, -1):
        if float(df.iloc[i]['close']) > threshold:
            count += 1
        else:
            break
    return count


# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def run_macro_gradient(profile="SWING", mode="INFO"):
    """
    Full Macro Gradient check per Doc 5 Sec II, II-A, 2.1, 2.2, 2.3.

    Evaluates:
      - SPY vs 50-SMA (with 0.1 ATR buffer + scaled confirmation)
      - TNX vs 50-SMA (4-tier regime)
      - Yield Acceleration (TNX sustainment protocol)
      - Storm Watch (VIX >= 25)
      - Volatility Expansion (HIGH RISK cascade)
      - ATR Lag Dampener (Volatility Shock)

    Args:
        profile: SWING (A), TREND (B), or WEALTH (C) -- determines confirmation resolution
        mode: INFO (paper port 4002) or LIVE (port 4001)

    Returns: (status, diagnostic, metrics) tuple
        status:     "GREEN" | "YELLOW" | "AMBIGUOUS" | "RED_UNCONFIRMED" |
                    "RED_CONFIRMED" | "GREY" | "GREY_UNCONFIRMED" | "BLACK"
        diagnostic: Human-readable explanation
        metrics:    Dict with full audit trail
    """

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 40 + (os.getpid() % 100)
    port = 4002 if mode.upper() == "INFO" else 4001

    ib = IB()
    metrics = {}

    # --- PROFILE VALIDATION ---
    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if profile.upper() not in VALID_PROFILES:
        return "ERROR", f"INVALID PROFILE: '{profile}'.", {}

    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping[profile.upper()]

    # Confirmation bar requirements per profile [Doc 5 Sec II-A, P2]
    confirm_map = {
        "A": {"bars_needed": 3, "bar_label": "hourly", "bar_res": "1 hour", "bar_dur": "5 D"},
        "B": {"bars_needed": 3, "bar_label": "daily",  "bar_res": "1 day",  "bar_dur": "1 M"},
        "C": {"bars_needed": 3, "bar_label": "daily",  "bar_res": "1 day",  "bar_dur": "1 M"},
    }
    confirm_cfg = confirm_map[p_code]

    try:
        ib.connect('127.0.0.1', port, clientId=unique_client_id)

        # =================================================================
        # PHASE 1: SPY DAILY DATA (SMA 50 + ATR 14)
        # [Doc 5 Sec II-A, P35: "remain daily computations regardless"]
        # =================================================================
        spy_contract = Stock("SPY", "SMART", "USD")
        spy_details = ib.reqContractDetails(spy_contract)
        if spy_details:
            spy_contract = spy_details[0].contract

        spy_daily_bars = ib.reqHistoricalData(
            spy_contract, '', '6 M', '1 day', 'TRADES', True
        )
        if not spy_daily_bars or len(spy_daily_bars) < 60:
            return "ERROR", (
                f"Insufficient SPY daily data "
                f"({len(spy_daily_bars) if spy_daily_bars else 0} bars, need 60+)."
            ), metrics

        df_spy = util.df(spy_daily_bars)
        df_spy.set_index('date', inplace=True)
        df_spy['SMA_50'] = df_spy['close'].rolling(50).mean()
        df_spy = compute_atr(df_spy, 14)

        # SMA of ATR (for Volatility Expansion check)
        df_spy['ATR_14_SMA_50'] = df_spy['ATR_14'].rolling(50).mean()

        last_spy = df_spy.iloc[-1]
        prev_spy = df_spy.iloc[-2] if len(df_spy) >= 2 else None

        spy_close = round(float(last_spy['close']), 2)
        spy_sma_50 = round(float(last_spy['SMA_50']), 2)
        spy_atr_14 = round(float(last_spy['ATR_14']), 2)
        spy_atr_sma_50 = round(float(last_spy['ATR_14_SMA_50']), 2) if pd.notna(last_spy['ATR_14_SMA_50']) else None

        if pd.isna(spy_sma_50) or pd.isna(spy_atr_14):
            return "ERROR", "SPY SMA 50 or ATR 14 is NaN -- insufficient daily history.", metrics

        metrics["Profile"] = f"{profile.upper()} ({p_code})"
        metrics["SPY_Close"] = spy_close
        metrics["SPY_SMA_50"] = spy_sma_50
        metrics["SPY_ATR_14"] = spy_atr_14

        # =================================================================
        # PHASE 2: 0.1 ATR AMBIGUITY BUFFER [Doc 5 Sec II-A, P1]
        # =================================================================
        buffer = round(0.1 * spy_atr_14, 2)
        buffer_upper = round(spy_sma_50 + buffer, 2)
        buffer_lower = round(spy_sma_50 - buffer, 2)
        spy_gap = round(spy_close - spy_sma_50, 2)
        spy_gap_atr = round(spy_gap / spy_atr_14, 3) if spy_atr_14 > 0 else 0

        metrics["Buffer_0_1_ATR"] = buffer
        metrics["Buffer_Upper"] = buffer_upper
        metrics["Buffer_Lower"] = buffer_lower
        metrics["SPY_Gap_from_SMA"] = spy_gap
        metrics["SPY_Gap_in_ATR"] = spy_gap_atr

        # Raw SPY signal
        if spy_close > buffer_upper:
            spy_signal = "ABOVE"
        elif spy_close < buffer_lower:
            spy_signal = "BELOW"
        else:
            spy_signal = "AMBIGUOUS"
        metrics["SPY_Signal"] = spy_signal

        # =================================================================
        # PHASE 3: TNX DAILY DATA (SMA 50 + SMA 10 + ATR 14)
        # [Doc 5 Sec II -- regime axis 2]
        # [Doc 5 Sec 2.1 -- Yield Acceleration needs SMA 10 + ATR 14]
        # =================================================================
        tnx_contract = Index("TNX", "CBOE")
        tnx_details = ib.reqContractDetails(tnx_contract)
        if tnx_details:
            tnx_contract = tnx_details[0].contract

        tnx_daily_bars = ib.reqHistoricalData(
            tnx_contract, '', '6 M', '1 day', 'TRADES', True
        )

        tnx_available = bool(tnx_daily_bars and len(tnx_daily_bars) >= 60)
        tnx_signal = "UNAVAILABLE"
        yield_accel = False
        yield_accel_sustained = False

        if tnx_available:
            df_tnx = util.df(tnx_daily_bars)
            df_tnx.set_index('date', inplace=True)
            df_tnx['SMA_50'] = df_tnx['close'].rolling(50).mean()
            df_tnx['SMA_10'] = df_tnx['close'].rolling(10).mean()
            df_tnx = compute_atr(df_tnx, 14)

            last_tnx = df_tnx.iloc[-1]
            prev_tnx = df_tnx.iloc[-2] if len(df_tnx) >= 2 else None

            tnx_close = round(float(last_tnx['close']), 2)
            tnx_sma_50 = round(float(last_tnx['SMA_50']), 2)
            tnx_sma_10 = round(float(last_tnx['SMA_10']), 2) if pd.notna(last_tnx['SMA_10']) else None
            tnx_atr_14 = round(float(last_tnx['ATR_14']), 2) if pd.notna(last_tnx['ATR_14']) else None

            metrics["TNX_Close"] = tnx_close
            metrics["TNX_SMA_50"] = tnx_sma_50
            metrics["TNX_SMA_10"] = tnx_sma_10
            metrics["TNX_ATR_14"] = tnx_atr_14

            # TNX regime axis: above or below 50-SMA
            if pd.notna(tnx_sma_50):
                tnx_signal = "ABOVE" if tnx_close > tnx_sma_50 else "BELOW"
            metrics["TNX_Signal"] = tnx_signal

            # -----------------------------------------------------------
            # YIELD ACCELERATION [Doc 5 Sec 2.1]
            # Trigger: TNX close > SMA_10 + 1.2 x ATR_14
            # Sustainment: Must hold for 2 consecutive daily closes
            # -----------------------------------------------------------
            if tnx_sma_10 is not None and tnx_atr_14 is not None:
                ya_threshold = round(tnx_sma_10 + 1.2 * tnx_atr_14, 2)
                metrics["Yield_Accel_Threshold"] = ya_threshold

                ya_today = tnx_close > ya_threshold
                ya_yesterday = False
                if prev_tnx is not None:
                    prev_sma_10 = df_tnx['SMA_10'].iloc[-2]
                    prev_atr_14 = df_tnx['ATR_14'].iloc[-2]
                    if pd.notna(prev_sma_10) and pd.notna(prev_atr_14):
                        ya_prev_threshold = float(prev_sma_10) + 1.2 * float(prev_atr_14)
                        ya_yesterday = float(prev_tnx['close']) > ya_prev_threshold

                yield_accel = ya_today
                yield_accel_sustained = ya_today and ya_yesterday

                metrics["Yield_Accel_Today"] = ya_today
                metrics["Yield_Accel_Yesterday"] = ya_yesterday
                metrics["Yield_Accel_Sustained"] = yield_accel_sustained
        else:
            metrics["TNX_Status"] = "INSUFFICIENT_DATA"
            metrics["TNX_Signal"] = "UNAVAILABLE"

        # =================================================================
        # PHASE 4: VIX DATA -- STORM WATCH [Doc 5 Sec 2.2]
        # Instant: VIX >= 25 -> 50% sizing reduction (first close)
        # =================================================================
        vix_contract = Index("VIX", "CBOE")
        vix_details = ib.reqContractDetails(vix_contract)
        if vix_details:
            vix_contract = vix_details[0].contract

        vix_daily_bars = ib.reqHistoricalData(
            vix_contract, '', '3 M', '1 day', 'TRADES', True
        )

        storm_watch = False
        vix_close = None
        vol_expansion_sustained = False

        if vix_daily_bars and len(vix_daily_bars) >= 2:
            df_vix = util.df(vix_daily_bars)
            df_vix.set_index('date', inplace=True)

            vix_close = round(float(df_vix.iloc[-1]['close']), 2)
            vix_prev = round(float(df_vix.iloc[-2]['close']), 2)

            storm_watch = vix_close >= 25.0
            metrics["VIX_Close"] = vix_close
            metrics["Storm_Watch"] = storm_watch
            if storm_watch:
                metrics["Storm_Watch_Action"] = "50% SIZING REDUCTION ACTIVE (immediate)"

            # -----------------------------------------------------------
            # VOLATILITY EXPANSION [Doc 5 Sec 2.2]
            # Condition: VIX >= 25 OR SPY ATR_14 > 1.5 x 50-SMA of ATR_14
            # Sustainment: 2 consecutive daily closes
            # Only triggers BLACK when COMBINED with Yield Acceleration
            # -----------------------------------------------------------
            ve_vix_today = vix_close >= 25.0
            ve_vix_yesterday = vix_prev >= 25.0

            ve_atr_today = False
            ve_atr_yesterday = False
            if spy_atr_sma_50 is not None:
                atr_expansion_threshold = round(1.5 * spy_atr_sma_50, 2)
                metrics["ATR_Expansion_Threshold"] = atr_expansion_threshold
                ve_atr_today = spy_atr_14 > atr_expansion_threshold
                if prev_spy is not None and pd.notna(prev_spy['ATR_14']) and pd.notna(prev_spy['ATR_14_SMA_50']):
                    ve_atr_yesterday = float(prev_spy['ATR_14']) > 1.5 * float(prev_spy['ATR_14_SMA_50'])

            ve_today = ve_vix_today or ve_atr_today
            ve_yesterday = ve_vix_yesterday or ve_atr_yesterday
            vol_expansion_sustained = ve_today and ve_yesterday

            metrics["Vol_Expansion_Today"] = ve_today
            metrics["Vol_Expansion_Yesterday"] = ve_yesterday
            metrics["Vol_Expansion_Sustained"] = vol_expansion_sustained
        else:
            metrics["VIX_Status"] = "INSUFFICIENT_DATA"

        # =================================================================
        # PHASE 5: ATR LAG DAMPENER -- VOLATILITY SHOCK [Doc 5 Sec 2.3]
        # Trigger: SPY ATR_14 increases by > 25% in a single session
        # =================================================================
        vol_shock = False
        if prev_spy is not None and pd.notna(prev_spy['ATR_14']) and float(prev_spy['ATR_14']) > 0:
            prev_atr = float(prev_spy['ATR_14'])
            atr_change_pct = round((spy_atr_14 - prev_atr) / prev_atr * 100, 2)
            vol_shock = atr_change_pct > 25.0
            metrics["ATR_Change_Pct"] = atr_change_pct
            metrics["Volatility_Shock"] = vol_shock
            if vol_shock:
                hw_tr = round(max(
                    float(last_spy['high']) - float(last_spy['low']),
                    abs(float(last_spy['high']) - float(prev_spy['close'])),
                    abs(float(last_spy['low']) - float(prev_spy['close']))
                ), 2)
                metrics["High_Water_TR"] = hw_tr
                metrics["Volatility_Shock_Action"] = (
                    f"ACTIVE: Use High-Water TR ({hw_tr}) instead of ATR_14 ({spy_atr_14}) "
                    f"for buffer and proximity calculations"
                )

        # =================================================================
        # PHASE 6: SPY SCALED CONFIRMATION (only if SPY BELOW buffer)
        # [Doc 5 Sec II-A, P2]
        # =================================================================
        spy_confirmed = False
        consec_below = 0

        if spy_signal == "BELOW":
            metrics["Confirmation_Required"] = True
            metrics["Confirmation_Bar_Type"] = confirm_cfg["bar_label"]
            metrics["Confirmation_Bars_Needed"] = confirm_cfg["bars_needed"]
            metrics["Confirmation_Boundary"] = buffer_lower

            confirm_bars = ib.reqHistoricalData(
                spy_contract, '', confirm_cfg["bar_dur"], confirm_cfg["bar_res"], 'TRADES', True
            )

            if confirm_bars and len(confirm_bars) >= 3:
                df_confirm = util.df(confirm_bars)
                consec_below = count_consecutive_below(df_confirm, buffer_lower)

            metrics["Consecutive_Below_Buffer"] = consec_below
            spy_confirmed = consec_below >= confirm_cfg["bars_needed"]

            # Profile C weekly alternative
            if p_code == "C" and not spy_confirmed:
                weekly_bars = ib.reqHistoricalData(
                    spy_contract, '', '2 M', '1 week', 'TRADES', True
                )
                if weekly_bars and len(weekly_bars) >= 1:
                    last_weekly = float(util.df(weekly_bars).iloc[-1]['close'])
                    weekly_below = last_weekly < buffer_lower
                    metrics["Weekly_Close"] = round(last_weekly, 2)
                    metrics["Weekly_Below_Buffer"] = weekly_below
                    if weekly_below:
                        spy_confirmed = True

            metrics["SPY_Confirmation_Met"] = spy_confirmed
        else:
            metrics["Confirmation_Required"] = False

        # =================================================================
        # PHASE 7: REGIME CLASSIFICATION
        # =================================================================

        # --- Overlay annotations (appended to any regime diagnostic) ---
        overlays = []
        if storm_watch:
            overlays.append("Storm Watch ACTIVE (50% sizing reduction)")
        if vol_shock:
            overlays.append(f"Volatility Shock ACTIVE (High-Water TR: {metrics.get('High_Water_TR','N/A')})")
        if yield_accel_sustained:
            overlays.append("Yield Acceleration SUSTAINED (2/2 daily closes)")
        elif yield_accel:
            overlays.append("Yield Acceleration triggered (1/2 daily closes -- monitoring)")
        if vol_expansion_sustained:
            overlays.append("Volatility Expansion SUSTAINED (2/2 daily closes)")
        overlay_str = (" | OVERLAYS: " + "; ".join(overlays)) if overlays else ""

        # --- BLACK override: Yield Accel + Vol Expansion both sustained ---
        # [Doc 5 Sec 2.2: "only triggers HARD HALT / FORCE HARVEST if
        #  mathematically combined with Yield Acceleration"]
        black_regime = yield_accel_sustained and vol_expansion_sustained
        metrics["BLACK_Regime"] = black_regime

        if black_regime:
            metrics["Regime"] = "BLACK"
            return (
                "BLACK",
                f"MACRO GRADIENT BLACK (HIGH RISK): "
                f"Yield Acceleration SUSTAINED (TNX {metrics.get('TNX_Close','N/A')} > "
                f"threshold {metrics.get('Yield_Accel_Threshold','N/A')} for 2 closes) "
                f"AND Volatility Expansion SUSTAINED (2 closes). "
                f"HARD HALT on ALL new entries. FORCE HARVEST on Weak positions."
                f"{overlay_str}",
                metrics
            )

        # --- SPY AMBIGUOUS: prior regime holds ---
        if spy_signal == "AMBIGUOUS":
            metrics["Regime"] = "AMBIGUOUS"
            return (
                "AMBIGUOUS",
                f"MACRO GRADIENT AMBIGUOUS: SPY close ({spy_close}) is WITHIN the "
                f"0.1 ATR noise buffer [{buffer_lower}, {buffer_upper}] around "
                f"SMA 50 ({spy_sma_50}). Gap: {spy_gap} ({spy_gap_atr} ATR). "
                f"System remains in PRIOR regime per Doc 5 Sec II-A and Sec IV."
                f"{overlay_str}",
                metrics
            )

        # --- SPY ABOVE: GREEN or YELLOW ---
        if spy_signal == "ABOVE":
            if tnx_signal == "BELOW" or tnx_signal == "UNAVAILABLE":
                metrics["Regime"] = "GREEN"
                tnx_note = (
                    f"TNX ({metrics.get('TNX_Close','N/A')}) BELOW "
                    f"50-SMA ({metrics.get('TNX_SMA_50','N/A')}) -- no yield pressure."
                ) if tnx_signal != "UNAVAILABLE" else (
                    "TNX data unavailable -- regime defaulted to GREEN."
                )
                return (
                    "GREEN",
                    f"MACRO GRADIENT GREEN (BULLISH): SPY close ({spy_close}) ABOVE "
                    f"buffer upper ({buffer_upper}). {tnx_note} "
                    f"Full engagement authorized."
                    f"{overlay_str}",
                    metrics
                )
            else:
                metrics["Regime"] = "YELLOW"
                return (
                    "YELLOW",
                    f"MACRO GRADIENT YELLOW (DEFENSIVE): SPY close ({spy_close}) ABOVE "
                    f"buffer ({buffer_upper}), but TNX ({metrics.get('TNX_Close','N/A')}) ABOVE "
                    f"50-SMA ({metrics.get('TNX_SMA_50','N/A')}) -- yield pressure. "
                    f"50% posture reduction mandated."
                    f"{overlay_str}",
                    metrics
                )

        # --- SPY BELOW: RED or GREY (depends on TNX + confirmation) ---
        if spy_signal == "BELOW":
            is_grey = (tnx_signal == "BELOW")
            regime_label = "GREY" if is_grey else "RED"

            if not spy_confirmed:
                shortfall = confirm_cfg["bars_needed"] - consec_below
                metrics["Regime"] = f"{regime_label}_UNCONFIRMED"
                return (
                    metrics["Regime"],
                    f"MACRO GRADIENT {regime_label} (UNCONFIRMED): "
                    f"SPY close ({spy_close}) BELOW buffer ({buffer_lower}), "
                    f"but confirmation NOT met: {consec_below}/{confirm_cfg['bars_needed']} "
                    f"{confirm_cfg['bar_label']} closes (need {shortfall} more). "
                    f"System remains in PRIOR regime."
                    f"{overlay_str}",
                    metrics
                )
            else:
                metrics["Regime"] = regime_label if not is_grey else "GREY"
                deflation_note = (
                    f" TNX ({metrics.get('TNX_Close','N/A')}) BELOW 50-SMA "
                    f"({metrics.get('TNX_SMA_50','N/A')}) -- deflationary pressure. "
                    f"Operationally equivalent to RED."
                ) if is_grey else (
                    f" TNX ({metrics.get('TNX_Close','N/A')}) ABOVE 50-SMA "
                    f"({metrics.get('TNX_SMA_50','N/A')}) -- yield pressure."
                )
                return (
                    metrics["Regime"],
                    f"MACRO GRADIENT {regime_label} ({'SHOCK/DEFLATION' if is_grey else 'CONFIRMED'}): "
                    f"SPY close ({spy_close}) BELOW buffer ({buffer_lower}) -- CONFIRMED "
                    f"({consec_below} {confirm_cfg['bar_label']} closes).{deflation_note} "
                    f"HARD HALT on new entries. FORCE HARVEST on Weak positions."
                    f"{overlay_str}",
                    metrics
                )

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", metrics
    finally:
        if ib.isConnected():
            ib.disconnect()


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBS Macro Gradient (Step 1) - Full Doc 5 Sec II: "
                    "SPY/TNX regime, Yield Acceleration, Storm Watch, Vol Expansion"
    )
    parser.add_argument("--profile", default="SWING",
                        help="Trade profile: SWING (A), TREND (B), WEALTH (C). "
                             "Determines confirmation bar resolution.")
    parser.add_argument("--mode", default="INFO",
                        help="INFO (paper/read-only port 4002) or LIVE (port 4001)")
    args = parser.parse_args()

    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if args.profile.upper() not in VALID_PROFILES:
        print(json.dumps({
            "status": "ERROR",
            "diagnostic": f"INVALID PROFILE: '{args.profile}'. "
                          f"Valid: SWING (A), TREND (B), WEALTH (C).",
            "metrics": {}
        }, indent=4))
        import sys
        sys.exit(1)

    status, diag, metrics = run_macro_gradient(args.profile, args.mode)
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))

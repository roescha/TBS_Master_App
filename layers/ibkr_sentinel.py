import argparse
import json
import asyncio
import os
import pandas as pd
import pandas_ta as ta
from typing import Optional, Tuple, Dict, Any

from ib_insync import IB, Contract, util


# -----------------------------
# TBS SENTINEL (Layer 0) v8.3
# Deterministic, profile-aware, hybrid shock mode
# Bug fixes: S-1 (DataFrame alignment), S-2 (daily SMA_50 for hourly confirmation),
#            S-5 (ATR vol expansion vs ATR_SMA_50, not price SMA)
# v8.3.1:   S-6 (Regime confirmation uses daily closes for ALL profiles including SWING;
#            hourly confirmation removed -- produced false SHOCK on normal intraday dips.
#            CLI --mode LIVE now defaults port to 4001)
#            S-6b (CLI useRTH default flipped to True; was False due to action=store_true
#            bug causing extended-hours closes to corrupt daily regime classification)
#            S-7 (prev_confirmed_regime: reduced lookback from 60 to 15, added permissive
#            grouping for BULLISH+DEFENSIVE to avoid stale SHOCK from months-old dips)
#            S-7b (AMBIGUOUS bars treated as compatible in permissive grouping; SPY near
#            SMA50 scatters AMBIGUOUS bars that were blocking every permissive window)
# -----------------------------

def run_tbs_sentinel(
        ib_connection: Optional[IB] = None,
        port: int = 4002,
        profile: str = "TREND",          # "SWING" | "TREND" | "WEALTH" or "A" | "B" | "C"
        useRTH: bool = True,
        debug: bool = False
) -> Tuple[str, str, str, bool, Dict[str, Any]]:
    """
    Returns:
        (regime, verdict, reason, storm_watch, details)

    Notes:
    - HIGH RISK cascade is ALWAYS computed from DAILY closes (2-day sustainment).
    - Standard regime confirmation is profile-bound:
        A: 3 consecutive DAILY closes beyond +/-0.1 buffer [S-6: was hourly, caused false SHOCK]
        B: 3 consecutive DAILY closes beyond +/-0.1 buffer
        C: 1 WEEKLY close beyond +/-0.1 buffer OR fallback to 3 DAILY closes
    - During Volatility Shock (SPY ATR_14 up > 25% day/day), ambiguity buffer uses running intraday TR.
    """

    # --- START: CRITICAL CONCURRENCY PATCH ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    unique_client_id = 10 + (os.getpid() % 100)
    # --- END CONCURRENCY PATCH ---

    # Normalize profile
    p = profile.strip().upper()
    if p in {"A", "PROFILE A"}:
        p = "SWING"
    elif p in {"B", "PROFILE B"}:
        p = "TREND"
    elif p in {"C", "PROFILE C"}:
        p = "WEALTH"
    if p not in {"SWING", "TREND", "WEALTH"}:
        p = "TREND"

    ib = ib_connection if ib_connection else IB()
    if not ib.isConnected():
        try:
            ib.connect("127.0.0.1", port, clientId=unique_client_id)
        except Exception as e:
            return "ERROR", "HALT", str(e), False, {}

    ib.reqMarketDataType(1)  #

    try:
        # --- Contracts (Systemic Proxies) ---
        spy = Contract(symbol="SPY", secType="STK", exchange="SMART", currency="USD")
        tnx = Contract(symbol="TNX", secType="IND", exchange="CBOE", currency="USD")
        vix = Contract(symbol="VIX", secType="IND", exchange="CBOE", currency="USD")

        # -----------------------------
        # Helper: request bars and validate
        # -----------------------------
        def req_df(contract: Contract, duration: str, bar_size: str, what: str = "TRADES"):
            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what,
                useRTH=useRTH,
                formatDate=1
            )
            df = util.df(bars)
            return df

        def halt_missing(reason: str):
            details = {"reason": reason, "profile": p}
            return "AMBIGUOUS", "HALT", f"Missing/invalid data: {reason}", False, details

        # -----------------------------
        # 1) DAILY SERIES (always) for:
        #    - Yield Acceleration (TNX)
        #    - Volatility Expansion (VIX or SPY ATR/SMA)
        #    - Volatility Shock detection (SPY ATR jump)
        # -----------------------------
        df_spy_d = req_df(spy, duration="9 M", bar_size="1 day")
        df_tnx_d = req_df(tnx, duration="9 M", bar_size="1 day")
        df_vix_d = req_df(vix, duration="3 M", bar_size="1 day")

        # Basic length guards (need SMA50 and ATR14 warmup)
        if df_spy_d is None or len(df_spy_d) < 70:
            return halt_missing("SPY daily bars < 70 (need SMA50/ATR14 warmup)")
        if df_tnx_d is None or len(df_tnx_d) < 70:
            return halt_missing("TNX daily bars < 70 (need SMA50/SMA10/ATR14 warmup)")
        if df_vix_d is None or len(df_vix_d) < 20:
            return halt_missing("VIX daily bars < 20")

        # Indicators (Daily)
        df_spy_d.ta.sma(length=50, append=True)   # SMA_50
        df_spy_d.ta.atr(length=14, append=True)   # ATRr_14
        # [S-5 FIX] SMA_50 of ATR_14 for Volatility Expansion (Doc 5 Sec2.2)
        # Compares current realised vol against its own 50-day average, not the price SMA.
        df_spy_d["ATR_SMA_50"] = df_spy_d["ATRr_14"].rolling(window=50).mean()

        df_tnx_d.ta.sma(length=10, append=True)   # SMA_10
        df_tnx_d.ta.sma(length=50, append=True)   # SMA_50
        df_tnx_d.ta.atr(length=14, append=True)   # ATRr_14

        # Validate indicator columns exist
        for col in ["SMA_50", "ATRr_14"]:
            if col not in df_spy_d.columns:
                return halt_missing(f"SPY daily missing indicator column {col}")
        for col in ["SMA_10", "SMA_50", "ATRr_14"]:
            if col not in df_tnx_d.columns:
                return halt_missing(f"TNX daily missing indicator column {col}")

        # -----------------------------
        # 2) DAILY HIGH-RISK CASCADE (2-day sustainment)
        # -----------------------------
        # Yield Acceleration: TNX close > SMA10 + 1.2*ATR14  (sustained 2 closes)
        y_accel_d = df_tnx_d["close"] > (df_tnx_d["SMA_10"] + (1.2 * df_tnx_d["ATRr_14"]))

        # [S-1 FIX] Volatility Expansion: evaluate last 2 bars directly to avoid
        # DataFrame misalignment between df_vix_d (3M) and df_spy_d (9M).
        # [S-5 FIX] ATR leg compares against its own 50-day SMA, not the price SMA.
        # Doc 5 Sec2.2: VIX >= 25 OR SPY ATR_14 > 1.5 x SMA_50(ATR_14)
        def _vol_expansion_at(spy_row, vix_row):
            vix_trigger = float(vix_row["close"]) >= 25.0
            atr_val = float(spy_row["ATRr_14"])
            atr_sma = float(spy_row["ATR_SMA_50"]) if not pd.isna(spy_row["ATR_SMA_50"]) else 0.0
            atr_trigger = atr_sma > 0 and atr_val > (1.5 * atr_sma)
            return bool(vix_trigger or atr_trigger)

        v_exp_last1 = _vol_expansion_at(df_spy_d.iloc[-1], df_vix_d.iloc[-1])
        v_exp_last2 = _vol_expansion_at(df_spy_d.iloc[-2], df_vix_d.iloc[-2])

        # Align last two bars safely
        if len(y_accel_d) < 2:
            return halt_missing("Not enough daily bars to evaluate 2-day sustainment")

        is_high_risk_today = bool(y_accel_d.iloc[-1] and y_accel_d.iloc[-2] and v_exp_last1 and v_exp_last2)

        # Storm Watch: instantaneous sizing reduction on first VIX close >= 25
        storm_watch = bool(float(df_vix_d["close"].iloc[-1]) >= 25.0)

        # -----------------------------
        # 3) VOLATILITY SHOCK DETECTION (daily ATR jump >25%)
        #    and Running Intraday True Range (hybrid path)
        # -----------------------------
        atr_prev = float(df_spy_d["ATRr_14"].iloc[-2])
        atr_curr = float(df_spy_d["ATRr_14"].iloc[-1])
        is_vol_shock = bool(atr_curr > (1.25 * atr_prev))

        running_true_range = None
        if is_vol_shock:
            # Use 1-minute SPY bars "today so far" to compute running intraday true range
            # Deterministic snapshot: if you want minute-refresh behavior (Profile A),
            # re-run this script each minute from the orchestrator during the first hour.
            df_spy_1m = req_df(spy, duration="1 D", bar_size="1 min")
            if df_spy_1m is None or len(df_spy_1m) < 2:
                return halt_missing("Volatility Shock active but SPY 1-min bars unavailable")

            # Running session high/low
            session_high = float(df_spy_1m["high"].max())
            session_low = float(df_spy_1m["low"].min())
            prev_close = float(df_spy_d["close"].iloc[-2])

            running_true_range = max(
                session_high - session_low,
                abs(session_high - prev_close),
                abs(session_low - prev_close)
            )

        # -----------------------------
        # 4) PROFILE-BOUND CONFIRMATION SERIES
        # [S-6] Regime confirmation always uses daily closes for all profiles.
        # The Macro Gradient (SPY vs 50-Day SMA) is a daily-close construct
        # per Doc 5 Sec II. Hourly bars produced false SHOCK signals on normal
        # intraday dips (SPY marginally below SMA50 for a few hours).
        # WEALTH retains weekly with daily fallback.
        # -----------------------------
        def confirmation_spec(profile_norm: str):
            if profile_norm == "SWING":
                return {"bar_size": "1 day", "duration": "9 M", "bars_required": 3}
            if profile_norm == "TREND":
                return {"bar_size": "1 day", "duration": "9 M", "bars_required": 3}
            # WEALTH: prefer weekly (1 close) and fallback daily (3 closes)
            return {"bar_size": "1 week", "duration": "5 Y", "bars_required": 1}

        spec = confirmation_spec(p)

        # Pull confirmation timeframe data
        df_spy_c = req_df(spy, duration=spec["duration"], bar_size=spec["bar_size"])
        df_tnx_c = req_df(tnx, duration=spec["duration"], bar_size=spec["bar_size"])

        if df_spy_c is None or df_tnx_c is None:
            return halt_missing("Confirmation timeframe bars unavailable (SPY/TNX)")
        if len(df_spy_c) < max(60, spec["bars_required"] + 2):
            # Need SMA50 warmup (60 bars minimum for daily/weekly)
            return halt_missing(f"Confirmation timeframe too short for SMA50 ({spec['bar_size']})")
        if len(df_spy_c) < spec["bars_required"] + 1:
            return halt_missing(f"Not enough confirmation bars ({spec['bar_size']})")

        # [S-6] All profiles now use daily or weekly bars — compute indicators directly.
        # The S-2 hourly merge path has been removed (hourly confirmation produced false
        # SHOCK signals on normal intraday dips).
        df_spy_c.ta.sma(length=50, append=True)
        df_spy_c.ta.atr(length=14, append=True)
        df_tnx_c.ta.sma(length=50, append=True)

        if "SMA_50" not in df_spy_c.columns or "ATRr_14" not in df_spy_c.columns:
            return halt_missing("Confirmation SPY missing SMA_50/ATRr_14")
        if "SMA_50" not in df_tnx_c.columns:
            return halt_missing("Confirmation TNX missing SMA_50")

        # -----------------------------
        # 5) Deterministic regime function (per-index; NO global contamination)
        # -----------------------------
        def regime_at(df_spy, df_tnx, idx: int, verbose: bool = False) -> Tuple[str, float]:
            """
            Returns (regime, buffer_used)
            buffer = 0.1 * ATR (normal)
            buffer = 0.1 * running_true_range (shock, latest bar only)
            """
            price = float(df_spy["close"].iloc[idx])
            spy_sma50 = float(df_spy["SMA_50"].iloc[idx])
            tnx_price = float(df_tnx["close"].iloc[idx])
            tnx_sma50 = float(df_tnx["SMA_50"].iloc[idx])

            if debug and verbose:
                print(
                    f"[DEBUG] idx={idx} SPY close={price:.2f} SMA50={spy_sma50:.2f} "
                    f"TNX close={tnx_price:.2f} SMA50={tnx_sma50:.2f}"
                )

            # Buffer selection
            if idx == -1 and is_vol_shock and (running_true_range is not None):
                buffer = 0.1 * float(running_true_range)
            else:
                buffer = 0.1 * float(df_spy["ATRr_14"].iloc[idx])

            # Ambiguity
            if abs(price - spy_sma50) <= buffer:
                return "AMBIGUOUS", buffer

            # Standard Macro Gradient
            if price > spy_sma50 and tnx_price < tnx_sma50:
                return "BULLISH (Blue)", buffer
            if price > spy_sma50 and tnx_price > tnx_sma50:
                return "DEFENSIVE (Yellow)", buffer
            if price < spy_sma50 and tnx_price > tnx_sma50:
                return "RESTRICTED (Red)", buffer
            if price < spy_sma50 and tnx_price < tnx_sma50:
                return "SHOCK (Grey)", buffer

            return "UNKNOWN", buffer

        # -----------------------------
        # 6) Confirmation check (profile-bound)
        # -----------------------------
        def confirmed_regime(df_spy, df_tnx, bars_required: int) -> Tuple[bool, str, str, float]:
            """
            Returns:
                (is_confirmed, cur_regime, reason, buffer_used_latest)
            """#

            regimes = []
            buffer_latest = None
            for k in range(bars_required, 0, -1):
                r, b = regime_at(df_spy, df_tnx, -k, verbose=True)
                regimes.append(r)
                if k == 1:
                    buffer_latest = b

            # --- DEBUG INSERT START ---
            if debug:
                print("\n[DEBUG] Confirmation regimes:")
                print(regimes)
                print("[DEBUG] Buffer used (latest):", buffer_latest)
            # --- DEBUG INSERT END ---
            cur = regimes[-1]

            # If ANY of the required confirmation bars is ambiguous, the whole confirmation fails as BUFFER ambiguity
            if "AMBIGUOUS" in regimes:
                return False, cur, "Signal within +/-0.1 buffer (deterministic ambiguity).", float(buffer_latest or 0.0)

            if cur == "AMBIGUOUS":
                return False, cur, "Signal within +/-0.1 buffer (deterministic ambiguity).", float(buffer_latest or 0.0)

            if not all(r == cur for r in regimes):
                return False, cur, f"Lacks {bars_required}-bar confirmation (regime flicker).", float(buffer_latest or 0.0)

            if cur in {"UNKNOWN"}:
                return False, cur, "Unknown regime classification.", float(buffer_latest or 0.0)

            return True, cur, "Regime confirmed by required consecutive closes.", float(buffer_latest or 0.0)



        def last_confirmed_regime(df_spy, df_tnx, bars_required: int, lookback: int = 15) -> Optional[str]:
            """
            Deterministically finds the most recent regime that achieved bars_required
            consecutive confirmations.

            [S-7] Lookback reduced from 60 to 15 bars. A confirmed SHOCK from 2 months
            ago is misleading when the recent state was BULLISH/DEFENSIVE. If no clean
            3-bar window exists in 15 bars, returns None (clearer than stale data).

            Additionally, permissive regimes (BULLISH + DEFENSIVE) are grouped: 3
            consecutive bars that are all permissive (any mix) count as confirmed,
            reporting the most recent of the group. This handles TNX SMA50 crossunder
            noise where BULLISH/DEFENSIVE alternate but the market posture is stable.

            [S-7b] AMBIGUOUS bars are treated as compatible with permissive regimes.
            When SPY oscillates near SMA50, AMBIGUOUS bars are scattered through the
            window. A window like [AMBIGUOUS, BULLISH, BULLISH] is permissive because
            AMBIGUOUS means "can't tell" — it should not block recognition that the
            surrounding context is clearly permissive. The latest non-AMBIGUOUS bar
            in the window determines the reported regime.
            """
            PERMISSIVE = {"BULLISH (Blue)", "DEFENSIVE (Yellow)"}
            PERMISSIVE_OR_AMBIGUOUS = PERMISSIVE | {"AMBIGUOUS"}
            n = min(len(df_spy), len(df_tnx))
            if n < bars_required:
                return None

            # scan from latest backward
            start_end = n - 1
            stop_end = max(bars_required - 1, n - lookback)

            for end_idx in range(start_end, stop_end - 1, -1):
                regimes = []
                for j in range(bars_required):
                    idx = end_idx - (bars_required - 1) + j
                    r, _ = regime_at(df_spy, df_tnx, idx)
                    regimes.append(r)

                cur = regimes[-1]
                if cur == "AMBIGUOUS":
                    continue

                # Strict match: all bars same regime
                if all(r == cur for r in regimes):
                    return cur

                # [S-7] Permissive grouping: if all bars are BULLISH or DEFENSIVE,
                # report the latest bar's regime as confirmed (market is stable even
                # if TNX flickers around its SMA50)
                if all(r in PERMISSIVE for r in regimes):
                    return cur

                # [S-7b] Permissive + AMBIGUOUS: if all bars are permissive or AMBIGUOUS
                # and at least one bar is a real permissive regime, report the latest
                # non-AMBIGUOUS bar as the confirmed regime.
                if all(r in PERMISSIVE_OR_AMBIGUOUS for r in regimes):
                    # Find latest non-AMBIGUOUS bar in window to report
                    for r in reversed(regimes):
                        if r in PERMISSIVE:
                            return r
                    continue  # all AMBIGUOUS (shouldn't happen since cur != AMBIGUOUS)

            return None


        is_confirmed, cur_regime, conf_reason, buffer_used = confirmed_regime(
            df_spy_c, df_tnx_c, bars_required=int(spec["bars_required"])
        )
        prev_confirmed = last_confirmed_regime(df_spy_c, df_tnx_c, int(spec["bars_required"]))

        # WEALTH fallback: if weekly path ambiguous/unconfirmed, try daily 3-bar
        used_fallback_daily = False
        if p == "WEALTH" and (not is_confirmed or cur_regime == "AMBIGUOUS"):
            # Daily fallback confirmation (3 daily closes) is allowed by spec
            df_spy_wd = df_spy_d.copy()
            df_tnx_wd = df_tnx_d.copy()
            # daily already has indicators computed above; ensure required columns exist:
            if "SMA_50" in df_spy_wd.columns and "ATRr_14" in df_spy_wd.columns and "SMA_50" in df_tnx_wd.columns:
                is_confirmed_d, cur_regime_d, conf_reason_d, buffer_used_d = confirmed_regime(df_spy_wd, df_tnx_wd, bars_required=3)
                if is_confirmed_d:
                    is_confirmed, cur_regime, conf_reason, buffer_used = is_confirmed_d, cur_regime_d, conf_reason_d, buffer_used_d
                    used_fallback_daily = True

        # -----------------------------
        # 7) Final decision logic (TBS precedence)
        #    - HIGH RISK (cascade) overrides standard regime
        #    - Otherwise require confirmation and non-ambiguity
        # -----------------------------
        details: Dict[str, Any] = {
            "profile": p,

            "current_snapshot_regime": cur_regime,
            "prev_confirmed_regime": prev_confirmed,
            "confirmation_bar_size": spec["bar_size"],
            "confirmation_bars_required": spec["bars_required"],
            "used_wealth_daily_fallback": used_fallback_daily,
            "storm_watch": storm_watch,
            "is_high_risk_today": is_high_risk_today,
            "is_vol_shock": is_vol_shock,
            "running_true_range": float(running_true_range) if running_true_range is not None else None,
            "buffer_used_latest": float(buffer_used),
            "vix_close": float(df_vix_d["close"].iloc[-1]),
            "spy_close_daily": float(df_spy_d["close"].iloc[-1]),
            "spy_atr14": float(df_spy_d["ATRr_14"].iloc[-1]),
            "spy_atr_sma50": float(df_spy_d["ATR_SMA_50"].iloc[-1]) if not pd.isna(df_spy_d["ATR_SMA_50"].iloc[-1]) else None,
            "vol_expansion_last1": v_exp_last1,
            "vol_expansion_last2": v_exp_last2,
            "tnx_close_daily": float(df_tnx_d["close"].iloc[-1]),
        }

        # HIGH RISK cascade (daily) has its own 2-day sustainment rule and implies emergency posture
        if is_high_risk_today:
            regime = "HIGH RISK (Black)"
            verdict = "FORCE HARVEST"
            reason = "HIGH RISK cascade confirmed (2-day sustainment: Yield Acceleration + Volatility Expansion)."
        else:
            if not is_confirmed:
                # If confirmation failed due to buffer ambiguity anywhere in the window, label as buffer ambiguity.
                if "buffer" in conf_reason.lower() or "ambiguous" in conf_reason.lower():
                    regime = "AMBIGUOUS (Buffer)"
                else:
                    regime = "UNCONFIRMED (Flicker)"
                verdict = "HALT"
                reason = conf_reason
            else:
                regime = cur_regime
                if regime in {"BULLISH (Blue)", "DEFENSIVE (Yellow)"}:
                    verdict = "PASS"
                elif regime == "SHOCK (Grey)":
                    verdict = "FORCE HARVEST"
                else:
                    verdict = "HALT"
                reason = "Regime mathematically confirmed."


        output = {
            "regime": regime,
            "verdict": verdict,
            "reason": reason,
            "storm_watch": storm_watch,
            "details": details if debug else {"profile": p, "vix": details["vix_close"], "tnx_close_daily": details["tnx_close_daily"]},
        }

        print(json.dumps(output, indent=4))
        return regime, verdict, reason, storm_watch, details

    except Exception as e:
        output = {
            "regime": "ERROR",
            "verdict": "HALT",
            "reason": str(e),
            "storm_watch": False,
            "details": {"profile": p}
        }
        print(json.dumps(output, indent=4))
        return "ERROR", "HALT", str(e), False, {"profile": p}
    finally:
        if not ib_connection:
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TBS Sentinel (Layer 0): Macro Gradient Engine")
    parser.add_argument("--profile", default="TREND", choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile driving confirmation timeframe (A=SWING, B=TREND, C=WEALTH).")
    parser.add_argument("--port", type=int, default=None, help="IBKR port (default: 4001 for LIVE, 4002 for INFO).")
    parser.add_argument("--no-rth", action="store_true",
                        help="Include extended hours data (default: RTH only).")
    parser.add_argument("--debug", action="store_true", help="Print expanded diagnostics.")
    parser.add_argument("--mode", default="INFO", choices=["LIVE", "INFO"],
                        help="LIVE (port 4001) or INFO (port 4002). Sets default port if --port not specified.")
    args = parser.parse_args()

    # [S-6] Mode-aware port: LIVE defaults to 4001, INFO defaults to 4002.
    # Explicit --port always takes priority.
    effective_port = args.port if args.port is not None else (4001 if args.mode.upper() == "LIVE" else 4002)

    run_tbs_sentinel(
        port=effective_port,
        profile=args.profile,
        useRTH=not args.no_rth,
        debug=args.debug,
    )
import argparse
import json
import asyncio
import os
import pandas_ta as ta
from typing import Optional, Tuple, Dict, Any

from ib_insync import IB, Contract, util


# -----------------------------
# TBS SENTINEL (Layer 0) v8.1
# Deterministic, profile-aware, hybrid shock mode
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
        A: 3 consecutive HOURLY closes beyond ±0.1 buffer
        B: 3 consecutive DAILY closes beyond ±0.1 buffer
        C: 1 WEEKLY close beyond ±0.1 buffer OR fallback to 3 DAILY closes
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

        # Volatility Expansion: VIX >= 25 OR SPY ATR14 > 1.5*SMA50 (sustained 2 closes)
        v_exp_d = (df_vix_d["close"] >= 25.0) | (df_spy_d["ATRr_14"] > (1.5 * df_spy_d["SMA_50"]))

        # Align last two bars safely
        if len(y_accel_d) < 2 or len(v_exp_d) < 2:
            return halt_missing("Not enough daily bars to evaluate 2-day sustainment")

        is_high_risk_today = bool(y_accel_d.iloc[-1] and y_accel_d.iloc[-2] and v_exp_d.iloc[-1] and v_exp_d.iloc[-2])

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
        # -----------------------------
        def confirmation_spec(profile_norm: str):
            if profile_norm == "SWING":
                return {"bar_size": "1 hour", "duration": "30 D", "bars_required": 3}
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
        if len(df_spy_c) < max(60, spec["bars_required"] + 2) and spec["bar_size"] != "1 hour":
            # For weekly/daily we need SMA50 warmup
            return halt_missing(f"Confirmation timeframe too short for SMA50 ({spec['bar_size']})")
        if len(df_spy_c) < spec["bars_required"] + 1:
            return halt_missing(f"Not enough confirmation bars ({spec['bar_size']})")

        # Indicators for confirmation timeframe
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
                return False, cur, "Signal within ±0.1 buffer (deterministic ambiguity).", float(buffer_latest or 0.0)

            if cur == "AMBIGUOUS":
                return False, cur, "Signal within ±0.1 buffer (deterministic ambiguity).", float(buffer_latest or 0.0)

            if not all(r == cur for r in regimes):
                return False, cur, f"Lacks {bars_required}-bar confirmation (regime flicker).", float(buffer_latest or 0.0)

            if cur in {"UNKNOWN"}:
                return False, cur, "Unknown regime classification.", float(buffer_latest or 0.0)

            return True, cur, "Regime confirmed by required consecutive closes.", float(buffer_latest or 0.0)



        def last_confirmed_regime(df_spy, df_tnx, bars_required: int, lookback: int = 60) -> Optional[str]:
            """
            Deterministically finds the most recent regime that achieved bars_required consecutive confirmations.
            Bounded by lookback to avoid unbounded scanning.
            Returns the regime string or None if not found.
            """
            n = min(len(df_spy), len(df_tnx))
            if n < bars_required:
                return None

            # scan from latest backward
            start_end = n - 1
            stop_end = max(bars_required - 1, n - lookback)

            for end_idx in range(start_end, stop_end - 1, -1):
                regimes = []
                ok = True
                for j in range(bars_required):
                    idx = end_idx - (bars_required - 1) + j
                    r, _ = regime_at(df_spy, df_tnx, idx)
                    regimes.append(r)

                cur = regimes[-1]
                if cur == "AMBIGUOUS":
                    continue
                if all(r == cur for r in regimes):
                    return cur

            return None


        is_confirmed, cur_regime, conf_reason, buffer_used = confirmed_regime(
            df_spy_c, df_tnx_c, bars_required=int(spec["bars_required"])
        )
        prev_confirmed = last_confirmed_regime(df_spy_c, df_tnx_c, int(spec["bars_required"]), lookback=60)

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
            "details": details if debug else {"profile": p, "vix": details["vix_close"]},
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
    parser.add_argument("--port", type=int, default=4002, help="IBKR port (4002 paper, 4001 live).")
    parser.add_argument("--useRTH", action="store_true", help="Use Regular Trading Hours only.")
    parser.add_argument("--debug", action="store_true", help="Print expanded diagnostics.")
    # Accept --mode for compatibility but do not use it here (it's for orchestrator)
    parser.add_argument("--mode", default="INFO", help="Accepted for compatibility; not used in Sentinel.")
    args = parser.parse_args()

    run_tbs_sentinel(
        port=args.port,
        profile=args.profile,
        useRTH=args.useRTH,
        debug=args.debug,
    )
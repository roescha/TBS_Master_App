import yfinance as yf
import json
import sys
import concurrent.futures # Required for the Timeout Guard

# -----------------------------
# TBS CLEAN TRADE AUDIT (Layer 1) v8.3
# Doc 6 compliance: Fundamental DNA, Pulse, and Quality Gates
# Bug fixes: Y-1 (ROIC None guard in Turnaround), Y-3 (Analyst retrieval escalation),
#            Y-5 (profile alias normalization)
# -----------------------------

def run_v8_clean_audit(ticker, profile="TREND", is_etf=False, wacc=None, moat=None, pivot_confirmed=False, roic_override=None):
    # [Y-5 FIX] Normalize profile aliases to canonical names
    p = profile.strip().upper()
    if p in ("A", "PROFILE A"):
        p = "SWING"
    elif p in ("B", "PROFILE B"):
        p = "TREND"
    elif p in ("C", "PROFILE C"):
        p = "WEALTH"
    if p not in ("SWING", "TREND", "WEALTH"):
        p = "TREND"  # Safe default

    # --- [MANDATE: DOC 6 SEC 8.1] DETERMINISTIC TIMEOUT GUARD ---
    # Prevents fundamental data hangs from stalling the Technical Engine
    def fetch_data():
        asset = yf.Ticker(ticker)
        return asset.info

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(fetch_data)
            try:
                info = future.result(timeout=60) # Mandated 60-second limit
            except concurrent.futures.TimeoutError:
                return "HALT (TIMEOUT)", "Network Timeout: Fundamental SSoT failed to respond in 60s.", {}

        # 1. FUNDAMENTAL DATA CAPTURE ONLY
        rev_growth = info.get('revenueGrowth')
        eps_growth = info.get('earningsGrowth')
        roic_raw = info.get('returnOnCapital')

        # [Y-3 NOTE] yfinance 'returnOnCapital' is unreliable: returns None for many tickers,
        # and may conflate ROE/ROIC depending on data provider. The --roic override flag is the
        # authoritative path. When ROIC is None, the script signals the Analyst to retrieve from
        # verified network sources (Morningstar, SEC filings) per Doc 6 Sec 3.5 / Doc 8 Sec 4.1.

        # Convert to percentages safely; preserve None for missing data
        rev_growth_pct = (rev_growth * 100) if rev_growth is not None else None
        eps_growth_pct = (eps_growth * 100) if eps_growth is not None else None
        if roic_raw is not None:
            roic_pct = roic_raw * 100.0
        elif roic_override is not None:
            roic_pct = float(roic_override)
        else:
            roic_pct = None

        # 2. DATA PACKAGING (Removed Volume/Liquidity Payload)
        metrics = {
            "ROIC": f"{roic_pct:.1f}%" if roic_pct is not None else "MASKED",
            "RevGrowth": f"{rev_growth_pct:.1f}%" if rev_growth_pct is not None else "MASKED",
            "EPSGrowth": f"{eps_growth_pct:.1f}%" if eps_growth_pct is not None else "MASKED"
        }

        # 3. [MANDATE: DOC 6] PROFILE A (SWING) & ETF EXEMPTIONS
        # Ensures bypass works whether passed as "SWING" or "A"
        if p == "SWING":
            return "CLEAN", "Profile A: Technical Focus. Fundamentals Bypassed.", metrics
        if is_etf:
            return "CLEAN", "ETF: Broad Index. Fundamental Growth Bypassed.", metrics

        # 3.1 [MANDATE: DOC 6] WEALTH MOAT REQUIREMENT (Operator-provided)
        # Morningstar Moat is not reliably available via yfinance; must be provided or HALT.
        if p == "WEALTH":
            moat_norm = (moat or "").strip().upper()
            if moat_norm not in ("WIDE", "NARROW"):
                return "HALT (MISSING DATA)", "Missing Data: WEALTH requires Moat rating (Wide or Narrow). Provide --moat WIDE|NARROW.", metrics


        # 4. MISSING DATA PENALTY (Profile-aware)
        # TREND requires Pulse only (Rev + EPS). WEALTH requires DNA + Pulse (ROIC + Rev + EPS).
        if p == "TREND":
            if rev_growth_pct is None or eps_growth_pct is None:
                return "HALT", f"Missing Data: Rev={metrics['RevGrowth']}, EPS={metrics['EPSGrowth']}", metrics

        elif p == "WEALTH":
            if rev_growth_pct is None or eps_growth_pct is None:
                return "HALT", f"Missing Data: Rev={metrics['RevGrowth']}, EPS={metrics['EPSGrowth']}", metrics
            if roic_pct is None:
                return "HALT (ANALYST RETRIEVE)", \
                    "Missing ROIC: yfinance returned None. Analyst is authorised to retrieve ROIC from " \
                    "verified network sources (Morningstar, SEC filings) per Doc 6 Sec 3.5. " \
                    "Re-run with --roic <value> once confirmed.", metrics

        # 5. THE WEALTH GATE (Profile C ROIC Mandate)
        wealth_failure = ""
        if p == "WEALTH":
            if roic_pct > 10.0 and rev_growth_pct > 0 and eps_growth_pct > 0:
                return "CLEAN", "Wealth Pulse Verified: ROIC > 10% and Quality Growth Positive.", metrics
            else:
                # Store the failure reason, but don't halt yet; check Turnaround Patch below
                wealth_failure = f"ROIC {roic_pct:.1f}% or Growth failed standard Wealth Gate."

        # 6. THE PULSE GATE (Profile B Growth Mandate)
        elif p == "TREND":
            if rev_growth_pct > 0 and eps_growth_pct > 0:
                return "CLEAN", "Pulse Verified: Quality & Growth Positive.", metrics

        # 7. THE TURNAROUND PATCH (Recovery Exception - Evaluated ONLY if standard gates fail)
        # [MANDATE: DOC 6 SEC 3.5] All 3 criteria must be met: Rev > 20%, ROIC > WACC, Pivot confirmed.
        if rev_growth_pct is not None and rev_growth_pct > 20.0:
            if not pivot_confirmed:
                return "HALT (PIVOT UNCONFIRMED)", "Turnaround Candidate Detected (Rev > 20%), but Pivot not confirmed (guidance revisions last 30d). Use --pivot-confirmed.", metrics
            # [Y-1 FIX] ROIC may be None for TREND (lighter gate doesn't require it) or
            # when yfinance returns None. Guard before comparison; escalate to Analyst retrieval.
            if roic_pct is None:
                return "HALT (ANALYST RETRIEVE)", \
                    "Turnaround Candidate (Rev > 20%, Pivot confirmed), but ROIC is missing. " \
                    "Analyst is authorised to retrieve ROIC from verified network sources " \
                    "(Morningstar, SEC filings) per Doc 6 Sec 3.5. Re-run with --roic <value>.", metrics
            if wacc is not None:
                if roic_pct > wacc:
                    return "CLEAN (TURNAROUND)", f"Turnaround Active: Rev > 20% and ROIC ({roic_pct:.1f}%) > WACC ({wacc:.1f}%). Mandate 0.5x Multiplier.", metrics
                else:
                    return "HALT", f"Turnaround Failed: ROIC ({roic_pct:.1f}%) < WACC ({wacc:.1f}%). Value destruction.", metrics
            else:
                return "HALT (MISSING DATA)", "Turnaround Candidate (Rev > 20%, ROIC available), but WACC data is missing. Use --wacc override.", metrics

        # 8. DEFAULT FAILURE (If it fails standard gates AND fails the Turnaround Patch)
        if p == "WEALTH":
            return "HALT", f"Thesis Breach: {wealth_failure}", metrics
        else:
            return "WEAKENED", "Negative or Stalled Growth Pulse.", metrics

    except Exception as e:
        return "ERROR", f"Audit Failed: {str(e)}", {}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--profile", default="TREND",
                        choices=["SWING", "TREND", "WEALTH", "A", "B", "C"],
                        help="Trade profile (A=SWING, B=TREND, C=WEALTH).")
    parser.add_argument("--etf", action="store_true")
    parser.add_argument("--wacc", type=float, default=None)
    parser.add_argument("--roic", type=float, default=None, help="Manual ROIC percent override (Analyst-retrieved). Example: --roic 12.5")
    parser.add_argument("--moat", type=str, default=None, help="Required for WEALTH (Wide or Narrow).")
    parser.add_argument("--pivot-confirmed", action="store_true", help="Turnaround Patch: confirm guidance revisions/pivot in last 30 days.")
    args = parser.parse_args()

    status, diag, metrics = run_v8_clean_audit(
        ticker=args.ticker,
        profile=args.profile,
        is_etf=args.etf,
        wacc=args.wacc,
        moat=args.moat,
        pivot_confirmed=args.pivot_confirmed,
        roic_override=args.roic,
    )
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}))
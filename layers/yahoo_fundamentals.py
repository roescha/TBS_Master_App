import yfinance as yf
import json
import sys
import concurrent.futures # Required for the Timeout Guard

# -----------------------------
# TBS CLEAN TRADE AUDIT (Layer 1) v8.3.1
# Doc 6 compliance: Fundamental DNA, Pulse, Financial Health, and Quality Gates
# Bug fixes: Y-1 (ROIC None guard in Turnaround), Y-3 (Analyst retrieval escalation),
#            Y-5 (profile alias normalization)
# v8.3.1:   Debt-to-Equity retrieval (Doc 6 Sec II), FCF Yield vs TNX gate (Doc 6 Sec 3.3),
#            --de, --fcf-yield, --rev, --eps Analyst override flags (Doc 6 Sec 3.5 Override Mandate)
# -----------------------------

def run_v8_clean_audit(ticker, profile="TREND", is_etf=False, wacc=None, moat=None, pivot_confirmed=False, roic_override=None, tnx=None, de_override=None, fcf_yield_override=None, rev_override=None, eps_override=None):
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

        # [v8.3.1] FINANCIAL HEALTH DATA (Doc 6 Sec II + Sec 3.3)
        debt_to_equity_raw = info.get('debtToEquity')       # yfinance returns as percentage (e.g. 150.0 = 150%)
        free_cash_flow = info.get('freeCashflow')            # absolute value in currency
        market_cap = info.get('marketCap')                   # absolute value in currency

        # [Y-3 NOTE] yfinance 'returnOnCapital' is unreliable: returns None for many tickers,
        # and may conflate ROE/ROIC depending on data provider. The --roic override flag is the
        # authoritative path. When ROIC is None, the script signals the Analyst to retrieve from
        # verified network sources (Morningstar, SEC filings) per Doc 6 Sec 3.5 / Doc 8 Sec 4.1.

        # Convert to percentages safely; preserve None for missing data
        rev_growth_pct = (rev_growth * 100) if rev_growth is not None else None
        eps_growth_pct = (eps_growth * 100) if eps_growth is not None else None

        # [v8.3.1] Rev/EPS overrides (Analyst-retrieved, already in percent)
        if rev_growth_pct is None and rev_override is not None:
            rev_growth_pct = float(rev_override)
        if eps_growth_pct is None and eps_override is not None:
            eps_growth_pct = float(eps_override)
        if roic_raw is not None:
            roic_pct = roic_raw * 100.0
        elif roic_override is not None:
            roic_pct = float(roic_override)
        else:
            roic_pct = None

        # [v8.3.1] Financial Health conversions
        # yfinance debtToEquity is already a percentage (e.g. 150.0 means 150%)
        if debt_to_equity_raw is not None:
            de_ratio = debt_to_equity_raw
        elif de_override is not None:
            de_ratio = float(de_override)
        else:
            de_ratio = None

        # FCF Yield = Free Cash Flow / Market Cap * 100 (as percentage)
        if fcf_yield_override is not None:
            fcf_yield_pct = float(fcf_yield_override)
        elif free_cash_flow is not None and market_cap is not None and market_cap > 0:
            fcf_yield_pct = (free_cash_flow / market_cap) * 100.0
        else:
            fcf_yield_pct = None

        # TNX comparison threshold (passed via --tnx or default 4.5%)
        tnx_yield = float(tnx) if tnx is not None else None

        # 2. DATA PACKAGING (Removed Volume/Liquidity Payload)
        metrics = {
            "ROIC": f"{roic_pct:.1f}%" if roic_pct is not None else "MASKED",
            "RevGrowth": f"{rev_growth_pct:.1f}%" if rev_growth_pct is not None else "MASKED",
            "EPSGrowth": f"{eps_growth_pct:.1f}%" if eps_growth_pct is not None else "MASKED",
            "DebtToEquity": f"{de_ratio:.1f}%" if de_ratio is not None else "MASKED",
            "FCFYield": f"{fcf_yield_pct:.2f}%" if fcf_yield_pct is not None else "MASKED",
            "TNXThreshold": f"{tnx_yield:.2f}%" if tnx_yield is not None else "NOT_PROVIDED"
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
                return "HALT (ANALYST RETRIEVE)", \
                    f"Missing Data: Rev={metrics['RevGrowth']}, EPS={metrics['EPSGrowth']}. " \
                    f"Analyst is authorised to retrieve from verified network sources " \
                    f"(Morningstar, SEC filings, macrotrends.net) per Doc 6 Sec 3.5. " \
                    f"Re-run with --rev <value> and/or --eps <value> once confirmed.", metrics

        elif p == "WEALTH":
            if rev_growth_pct is None or eps_growth_pct is None:
                return "HALT (ANALYST RETRIEVE)", \
                    f"Missing Data: Rev={metrics['RevGrowth']}, EPS={metrics['EPSGrowth']}. " \
                    f"Analyst is authorised to retrieve from verified network sources " \
                    f"(Morningstar, SEC filings, macrotrends.net) per Doc 6 Sec 3.5. " \
                    f"Re-run with --rev <value> and/or --eps <value> once confirmed.", metrics
            if roic_pct is None:
                return "HALT (ANALYST RETRIEVE)", \
                    "Missing ROIC: yfinance returned None. Analyst is authorised to retrieve ROIC from " \
                    "verified network sources (Morningstar, SEC filings) per Doc 6 Sec 3.5. " \
                    "Re-run with --roic <value> once confirmed.", metrics
            # [v8.3.1] Doc 6 Sec II: D/E and FCF Yield are required inputs for WEALTH.
            # Missing = HALT per the Missing Data Penalty mandate.
            if de_ratio is None:
                return "HALT (ANALYST RETRIEVE)", \
                    "Missing Data: Debt-to-Equity unavailable from yfinance. " \
                    "Analyst is authorised to retrieve D/E from verified network sources " \
                    "(Morningstar, SEC filings, macrotrends.net) per Doc 6 Sec 3.5. " \
                    "Re-run with --de <value> once confirmed.", metrics
            if fcf_yield_pct is None:
                return "HALT (ANALYST RETRIEVE)", \
                    "Missing Data: FCF Yield unavailable (freeCashflow or marketCap missing). " \
                    "Analyst is authorised to retrieve FCF Yield from verified network sources " \
                    "(Morningstar, SEC filings, macrotrends.net) per Doc 6 Sec 3.5. " \
                    "Re-run with --fcf-yield <value> once confirmed.", metrics

        # 5. THE WEALTH GATE (Profile C ROIC Mandate + Financial Health)
        wealth_failure = ""
        if p == "WEALTH":
            if roic_pct > 10.0 and rev_growth_pct > 0 and eps_growth_pct > 0:
                # [v8.3.1] Doc 6 Sec 3.3: FCF Yield Comparison vs TNX
                # "should be competitive" = soft gate (warning, not HALT)
                fcf_note = ""
                if tnx_yield is not None:
                    if fcf_yield_pct < tnx_yield:
                        fcf_note = (
                            f" WARNING: FCF Yield ({fcf_yield_pct:.2f}%) < TNX ({tnx_yield:.2f}%). "
                            f"Yield not competitive per Doc 6 Sec 3.3. Monitor for deterioration."
                        )
                        metrics["FCF_vs_TNX"] = "BELOW (not competitive)"
                    else:
                        fcf_note = f" FCF Yield ({fcf_yield_pct:.2f}%) >= TNX ({tnx_yield:.2f}%): competitive."
                        metrics["FCF_vs_TNX"] = "ABOVE (competitive)"
                else:
                    fcf_note = " FCF Yield vs TNX: comparison skipped (--tnx not provided)."
                    metrics["FCF_vs_TNX"] = "SKIPPED (no --tnx)"

                # D/E reported for operator awareness (Doc 6 Sec II lists it as required input)
                metrics["DebtToEquity_Note"] = f"D/E = {de_ratio:.1f}%. Reported for Financial Health assessment."

                return "CLEAN", f"Wealth Pulse Verified: ROIC > 10% and Quality Growth Positive.{fcf_note}", metrics
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
    parser.add_argument("--rev", type=float, default=None, help="Manual Revenue Growth percent override (Analyst-retrieved). Example: --rev 6.8")
    parser.add_argument("--eps", type=float, default=None, help="Manual EPS Growth percent override (Analyst-retrieved). Example: --eps 8.5")
    parser.add_argument("--de", type=float, default=None, help="Manual Debt-to-Equity percent override (Analyst-retrieved). Example: --de 139.8")
    parser.add_argument("--fcf-yield", type=float, default=None, help="Manual FCF Yield percent override (Analyst-retrieved). Example: --fcf-yield 3.5")
    parser.add_argument("--moat", type=str, default=None, help="Required for WEALTH (Wide or Narrow).")
    parser.add_argument("--tnx", type=float, default=None, help="Current 10-Year Treasury Yield for FCF Yield comparison (e.g. --tnx 4.03). Get from macro_gradient output.")
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
        tnx=args.tnx,
        de_override=args.de,
        fcf_yield_override=args.fcf_yield,
        rev_override=args.rev,
        eps_override=args.eps,
    )
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}))
#!/usr/bin/env python3
"""thesis_fundamentals.py — desk-tier numbers for the Thesis Inspector board, in its Import format.

Usage (evening routine):
    python thesis_fundamentals.py LLY MSFT AVGO NVDA CRH RKLB GLW ALAB CEG
    python thesis_fundamentals.py --file names.txt            # one ticker per line, or space/comma separated
    python thesis_fundamentals.py ... --out thesis_desk_2026-09-13.json
Then on the board: Import → pick the file. Every listed name is (re)written with source "yahoo quoteSummary" and today's date.

Needs:  pip install requests   (Python 3.9+). Uses Yahoo's public quoteSummary with the cookie+crumb handshake (no yfinance).
Written Sun Sep 13 2026 (Fable 5.1) for ledger #122. Standalone — does not depend on the TBS app.

What Yahoo carries → board field
  trailingPE → pe · epsTrailingTwelveMonths → eps · forwardPE → fpe · pegRatio (or trailingPegRatio) → peg
  priceToSalesTrailing12Months → ps · revenueGrowth → revg (%) · earningsGrowth (or earningsQuarterlyGrowth) → epsg (%)
  freeCashflow ÷ marketCap → fcfy (%) · debtToEquity → de (Yahoo reports it in %, divided by 100 here)
  targetMedianPrice / targetLowPrice / targetHighPrice / numberOfAnalystOpinions → tmed / tlow / thigh / tn
  EPS revisions: from the earnings-trend table (current-year estimate now vs 30 days ago) → epsrev up / flat / down
  Margin trend: operating margin (ttm, financialData) vs the latest fiscal year's (fundamentals-timeseries) → expanding / flat / contracting
What Yahoo does NOT carry (left for the desk, kept if already on the board):
  secpe — sector median forward P/E (seeded here from a fixed table per Yahoo sector, marked in the source; override on the board)
  fv / fvsrc / fvdate — a DCF fair value (Morningstar or similar); informational only on the board.
"""
import sys, json, argparse, datetime, math

# Seed sector-median forward P/E — a desk table, NOT a live number. Rough medians for the S&P sectors, mid-2026; edit as the
# TBS valuation table says. The board prints "fwd P/E n.nn× of <secpe>" so the seed is always visible.
SECTOR_FPE = {"Technology": 27.0, "Communication Services": 19.0, "Consumer Cyclical": 22.0, "Consumer Defensive": 19.0,
              "Healthcare": 17.0, "Financial Services": 14.0, "Industrials": 21.0, "Basic Materials": 16.0, "Energy": 13.0,
              "Utilities": 17.0, "Real Estate": 30.0}

def num(x):
    try:
        if x is None: return None
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None

def r(x, d=2):
    return None if x is None else round(x, d)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
MODULES = "summaryDetail,defaultKeyStatistics,financialData,earningsTrend,assetProfile,price"

def session():
    """Yahoo's cookie + crumb handshake (the same one yfinance does). Plain requests, no other dependency."""
    import requests
    s = requests.Session(); s.headers["User-Agent"] = UA
    try: s.get("https://fc.yahoo.com", timeout=20)          # sets the cookie (404 is normal)
    except Exception: pass
    crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20).text.strip()
    if not crumb or "<" in crumb: raise RuntimeError("no crumb from Yahoo (cookie handshake failed)")
    s.crumb = crumb; return s

def raw(d, *keys):
    for k in keys:
        if d is None: return None
        d = d.get(k) if isinstance(d, dict) else None
    if isinstance(d, dict): d = d.get("raw")
    return num(d)

def eps_revision(q):
    """up / flat / down: current-year EPS estimate now vs 30 days ago (earningsTrend, period 0y); '' if unavailable."""
    try:
        for tr in (q.get("earningsTrend") or {}).get("trend") or []:
            if tr.get("period") == "0y":
                now = raw(tr, "epsTrend", "current"); ago = raw(tr, "epsTrend", "30daysAgo")
                if now is not None and ago not in (None, 0):
                    ch = now / ago - 1
                    return "up" if ch > 0.01 else ("down" if ch < -0.01 else "flat")
    except Exception: pass
    return ""

def margin_trend(q, sym, s):
    """operating margin ttm (financialData) vs the latest fiscal year's operating margin (fundamentals-timeseries, annual)."""
    try:
        cur = raw(q, "financialData", "operatingMargins")
        if cur is None: return ""
        u = (f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
             f"?type=annualOperatingIncome,annualTotalRevenue&period1=1500000000&period2=2000000000&crumb={s.crumb}")
        j = s.get(u, timeout=30).json(); oi = rev = None
        for r_ in (j.get("timeseries") or {}).get("result") or []:
            if r_.get("annualOperatingIncome"): oi = num(r_["annualOperatingIncome"][-1]["reportedValue"]["raw"])
            if r_.get("annualTotalRevenue"): rev = num(r_["annualTotalRevenue"][-1]["reportedValue"]["raw"])
        if oi is None or not rev: return ""
        d = cur - oi / rev
        return "expanding" if d > 0.01 else ("contracting" if d < -0.01 else "flat")
    except Exception: return ""

def one(sym, today, s):
    u = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={MODULES}&crumb={s.crumb}"
    j = s.get(u, timeout=30).json(); res = (j.get("quoteSummary") or {}).get("result") or []
    if not res: raise RuntimeError(((j.get("quoteSummary") or {}).get("error") or {}).get("description") or "empty reply")
    q = res[0]; sd, ks, fd, ap = q.get("summaryDetail") or {}, q.get("defaultKeyStatistics") or {}, q.get("financialData") or {}, q.get("assetProfile") or {}
    mcap = raw(sd, "marketCap") or raw(q, "price", "marketCap"); fcf = raw(fd, "freeCashflow")
    sector = ap.get("sector") or ""
    eg = raw(fd, "earningsGrowth"); eg = eg if eg is not None else raw(ks, "earningsQuarterlyGrowth")
    peg = raw(ks, "pegRatio"); peg = peg if peg is not None else raw(ks, "trailingPegRatio")
    fpe = raw(sd, "forwardPE"); fpe = fpe if fpe is not None else raw(ks, "forwardPE")
    de = raw(fd, "debtToEquity")
    d = {
        "pe": r(raw(sd, "trailingPE")), "eps": r(raw(ks, "trailingEps")), "fpe": r(fpe), "peg": r(peg),
        "ps": r(raw(sd, "priceToSalesTrailing12Months")),
        "revg": r(100 * raw(fd, "revenueGrowth"), 1) if raw(fd, "revenueGrowth") is not None else None,
        "epsg": r(100 * eg, 1) if eg is not None else None,
        "fcfy": r(100 * fcf / mcap, 2) if (fcf is not None and mcap) else None,
        "de": r(de / 100, 2) if de is not None else None,
        "tmed": r(raw(fd, "targetMedianPrice")), "tlow": r(raw(fd, "targetLowPrice")), "thigh": r(raw(fd, "targetHighPrice")),
        "tn": int(raw(fd, "numberOfAnalystOpinions") or 0) or None,
        "epsrev": eps_revision(q), "margin": margin_trend(q, sym, s),
        "sector": sector, "secpe": SECTOR_FPE.get(sector),
        "src": "yahoo quoteSummary" + ("; secpe = desk sector table" if SECTOR_FPE.get(sector) else ""), "date": today,
    }
    return {k: ("" if v is None else v) for k, v in d.items()}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("names", nargs="*"); ap.add_argument("--file"); ap.add_argument("--out"); ap.add_argument("--date", help="as-of date to stamp (default: today)")
    a = ap.parse_args(); names = list(a.names)
    if a.file:
        names += [x for x in open(a.file).read().replace(",", " ").split()]
    names = [n.strip().upper() for n in names if n.strip()]
    if not names: print(__doc__); sys.exit(1)
    today = a.date or datetime.date.today().isoformat(); out = {}; ses = session()
    for s in names:
        try:
            out[s] = one(s, today, ses); print(f"{s:6s} pe {out[s]['pe']} fpe {out[s]['fpe']} peg {out[s]['peg']} tmed {out[s]['tmed']} n {out[s]['tn']} rev {out[s]['epsrev'] or '-'} margin {out[s]['margin'] or '-'} sector {out[s]['sector']}")
        except Exception as e:
            print(f"{s:6s} FAILED: {e}")
    fn = a.out or f"thesis_desk_{today}.json"
    json.dump(out, open(fn, "w"), indent=1); print(f"\nwrote {fn} — on the board: Import → pick this file. Existing fv / secpe values you typed are kept only if you re-enter them; the import overwrites each listed name.")

if __name__ == "__main__":
    main()

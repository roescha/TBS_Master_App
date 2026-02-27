# TBS Finviz Screener Parameters — Profile A, B, C

> **Purpose:** Pre-filter the stock universe to find candidates likely to pass the TBS engine gates.
> Finviz narrows 5,000+ stocks to 20-50 names → feed results into `ibkr_purity_engine.py` for full audit.
>
> **Limitation:** Finviz uses daily data only. Profile A (hourly VWAP) cannot be directly screened —
> the daily approximation below identifies stocks in the right *zone* for hourly pullback setups.
> Profile B and C map more directly to Finviz's daily/weekly SMA filters.

---

## PROFILE A — SWING (Hourly VWAP Pullback)

**What we're looking for:** Stocks in a daily uptrend that have pulled back intraday — candidates for hourly VWAP mean-reversion entries.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Liquidity — ADV gate |
| Descriptive | Average Volume | Over 1M | Hourly timeframe needs deep liquidity |
| Descriptive | Country | USA | Avoids ADR complications |
| Technical | 20-Day SMA | Price above SMA20 | Short-term trend intact |
| Technical | 50-Day SMA | SMA50 above SMA200 | Structural uptrend confirmed |
| Technical | 200-Day SMA | Price above SMA200 | Above structural floor |
| Technical | Performance | Week -2% to 0% | Recent pullback (dip into VWAP zone) |
| Technical | RSI (14) | 40 to 60 | Not overbought, not oversold — mean reversion zone |
| Technical | Beta | Under 2.0 | Avoids excessively volatile names |

**Post-Finviz:** Run as `--profile=SWING --mode=INFO`. Engine checks hourly VWAP, ATR proximity, EMA 8 > EMA 21, +DI > -DI.

---

## PROFILE B — TREND (Daily 50-SMA Pullback)

**What we're looking for:** Stocks in confirmed daily uptrends pulling back to the 50-SMA floor — standard trend continuation entries.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Liquidity — ADV gate |
| Descriptive | Average Volume | Over 500K | Daily timeframe liquidity |
| Descriptive | Country | USA | Avoids ADR complications |
| Technical | 50-Day SMA | Price above SMA50 | Above structural floor (or use "Price below SMA50" to find floor tests) |
| Technical | 200-Day SMA | SMA200 below SMA50 | Confirmed uptrend — 50 above 200 |
| Technical | 20-Day SMA | Price below SMA20 | Short-term weakness = pullback in progress |
| Technical | Performance | Month -5% to 0% | Recent correction toward floor |
| Technical | Beta | Under 1.5 | Filters out excessively volatile names |

**Variation — Floor Test (more aggressive):**
Change 50-Day SMA to **"Price below SMA50"** to find stocks that have dipped *through* the 50-day. These are potential reclaim setups if they close back above.

**Post-Finviz:** Run as `--profile=TREND --mode=INFO`. Engine checks Daily 50-SMA proximity, ADX > 25, full MA stack, Extension Audit (1.0 ATR from EMA 21).

---

## PROFILE C — WEALTH (Weekly 200-SMA Proximity)

**What we're looking for:** Quality large-caps in secular uptrends that have corrected to within 8% of the Weekly 200-SMA — optimal wealth accumulation entries.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Institutional quality |
| Descriptive | Average Volume | Over 500K | Liquidity — ADV gate |
| Descriptive | Country | USA | Avoids ADR complications |
| Technical | 200-Day SMA | Price above SMA200 | Floor intact — not broken |
| Technical | 50-Day SMA | Price below SMA50 | Pulled back from recent highs toward floor |
| Technical | Beta | Under 1.5 | Wealth profile = lower volatility |

**Post-Finviz:** Run as `--profile=WEALTH --mode=INFO`. Engine checks Weekly 200-SMA (not daily), Floor_Prox_Pct < 8%, +DI > -DI, Engine State.

**Note:** Finviz uses the *daily* 200-SMA, not the *weekly* 200-SMA. The daily 200-SMA ≈ 40-week SMA, which is close but not identical to the weekly 200-SMA used by the engine. Treat Finviz results as candidates, not confirmations — the engine is the final authority.

---

## BONUS: STRUCTURAL RECLAIM SCAN (REL-type setups)

**What we're looking for:** Stocks that have broken below the 200-SMA and are now climbing back toward it — potential reclaim entries after structural damage.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Avoids junk |
| Descriptive | Average Volume | Over 500K | Liquidity |
| Technical | 200-Day SMA | Price below SMA200 | Currently broken — below floor |
| Technical | Performance | Week +2% or more | Bouncing — recovery in progress |
| Technical | 52-Week High/Low | 20-30% below high | Significant correction (not a falling knife at 50%+) |
| Technical | Beta | Under 2.0 | Not excessively volatile |

**Post-Finviz:** Run as `--profile=TREND --mode=INFO` first (Daily 50-SMA is closer). Watch for Floor_Failure_Reclaim progressing 1/3 → 2/3 → 3/3. Only enter after full reclaim + Engine State upgrade to RESOLVING or TRENDING.

---

## QUICK REFERENCE: ENGINE COMMANDS

```
ibkr_purity_engine.py --ticker=XXXX --profile=SWING  --mode=INFO
ibkr_purity_engine.py --ticker=XXXX --profile=TREND  --mode=INFO
ibkr_purity_engine.py --ticker=XXXX --profile=WEALTH --mode=INFO
```

## WORKFLOW

1. Run Finviz scan (weekly for C, daily for A/B)
2. Note interesting names from sectors you lack exposure to
3. Feed into engine for full TBS audit
4. Engine PASS → evaluate position sizing via Governor (Doc 3)
5. Engine HALT → note reason, add to watchlist, re-scan next period

---

*For LSE-listed stocks: use TradingView screener (tradingview.com/screener) with equivalent filters — Finviz covers US markets only.*

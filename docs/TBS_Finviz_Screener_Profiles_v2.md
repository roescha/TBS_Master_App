# TBS Finviz Screener Parameters — Profile A, B, C
## v2.0 — Updated for PE-CAL-1 Gate Calibration

> **Purpose:** Pre-filter the stock universe to find candidates likely to pass the TBS engine gates.
> Finviz narrows 5,000+ stocks to 20-50 names → feed results into `ibkr_purity_engine.py` for full audit.
>
> **Limitation:** Finviz uses daily data only. Profile A (hourly VWAP) cannot be directly screened —
> the daily approximation below identifies stocks in the right *zone* for hourly pullback setups.
> Profile B and C map more directly to Finviz's daily/weekly SMA filters.
>
> **Governing Principle (PE-CAL-1):** The asset determines the profile, not the other way around.
> Classify the asset first (C-1 through C-4), then consult the Convexity-to-Profile routing table.
> These screeners identify candidates by structural pattern — the engine enforces the routing.

---

## ASSET-FIRST ROUTING TABLE

Before running any screener, know what you're looking for:

| Convexity | Examples | Primary Profile | Notes |
|-----------|----------|-----------------|-------|
| C-1 | VWRP, SPY, QQQ, Index ETFs | Profile A (Swing) or C (Wealth) | Bounded payoff, session-timeframe |
| C-2 | AAPL, MSFT, GOOGL, META, BHP, GLEN.L, CCJ, CRH | Profile B (Trend) or C (Wealth) | Moderate drawdowns, daily management |
| C-3 | IE, PAF.L, VZLA, ASTS | Profile B (Trend) only | Unbounded payoff, high volatility |
| C-4 | Pre-revenue biotech, SPACs | No profile — excluded from TBS | Reserved for future Protocol D |

---

## PROFILE A — SWING (Hourly VWAP Pullback)

**Target assets:** C-1 large-caps with bounded, predictable ranges. Session-timeframe mean-reversion.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Liquidity — ADV gate |
| Descriptive | Average Volume | Over 1M | Hourly timeframe needs deep liquidity |
| Descriptive | Country | USA | LSE names → use TradingView (see note below) |
| Technical | 20-Day SMA | Price above SMA20 | Short-term trend intact |
| Technical | 50-Day SMA | SMA50 above SMA200 | Structural uptrend confirmed |
| Technical | 200-Day SMA | Price above SMA200 | Above structural floor |
| Technical | Performance | Week -3% to +1% | Pullback zone — wider than pure dip, VWAP pullbacks can occur on flat/up weeks |
| Technical | Beta | Under 1.5 | C-1 character — low volatility, bounded range |

**Post-Finviz:** Run as `--profile=SWING --mode=INFO`. Engine checks hourly VWAP proximity, ATR distance (1.5 ATR limit), EMA 8 > EMA 21, +DI > -DI, 4-bar execution window.

**Note:** RSI is intentionally excluded. The engine uses VWAP proximity, not RSI. A stock at RSI 35 sitting on VWAP is a valid Profile A candidate — an RSI filter would exclude it.

---

## PROFILE B — TREND (Daily 50-SMA Pullback)

**Target assets:** C-2 and C-3 names in confirmed daily uptrends pulling back to the SMA 50 / EMA 21 zone.

### Scan 1: C-2 Trend Continuation (Moderate Volatility)

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Institutional quality |
| Descriptive | Average Volume | Over 500K | Daily timeframe liquidity |
| Descriptive | Country | USA | LSE names → use TradingView |
| Technical | 50-Day SMA | Price above SMA50 | Above structural floor |
| Technical | 200-Day SMA | SMA200 below SMA50 | Confirmed uptrend — 50 above 200 |
| Technical | 20-Day SMA | Price below SMA20 | Short-term weakness = pullback in progress |
| Technical | Performance | Quarter -10% to 0% | Wider window — PE-CAL-1 pullback zone extends to EMA 21 + 0.5 ATR |
| Technical | Beta | Under 1.5 | C-2 character |

### Scan 2: C-3 Convex Setups (High Volatility)

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Small (over $300mln) | C-3 names are often smaller |
| Descriptive | Average Volume | Over 500K | Liquidity floor |
| Descriptive | Country | USA | LSE names → use TradingView |
| Technical | 50-Day SMA | Price above SMA50 | Above structural floor |
| Technical | 200-Day SMA | SMA200 below SMA50 | Confirmed uptrend |
| Technical | Performance | Quarter -20% to 0% | C-3 drawdowns are larger — 20%+ pullbacks are routine |
| Technical | Beta | Over 1.5 | C-3 character — high volatility is the point |
| Descriptive | Industry | Gold, Uranium, Rare Earths, Biotech (Phase 3+), Exploration | Sector filter for convex themes |

### Scan 3: Floor Test (Aggressive — Both C-2 and C-3)

Change 50-Day SMA to **"Price below SMA50"** to find stocks that have dipped *through* the 50-day floor. These are potential reclaim setups (like IE at 1/3 reclaim).

**Post-Finviz (all Profile B scans):** Run as `--profile=TREND --mode=INFO`. Engine checks:
- Daily 50-SMA floor integrity
- ADX > 20 (not 25 — RESOLVING activates at 20)
- Pullback zone: [SMA 50, EMA 21 + 0.5 ATR] — PE-CAL-1 widened zone
- Extension limit: 1.0 ATR from EMA 21 (TRENDING) or 0.5 ATR from EMA 8 (RESOLVING, pre-breakout)
- Breakout extension exemption: 1.5 ATR ceiling on breakout bars (PE-CAL-1 §6.2)
- Window: 5-bar limit, resets on pullback, breakout, OR ADX cross above 20 (PE-CAL-1 §6.3)

---

## PROFILE C — WEALTH (Weekly 200-SMA Proximity)

**Target assets:** C-1 quality compounders in secular uptrends that have corrected toward the Weekly 200-SMA — optimal wealth accumulation entries. These are rare by design.

### Scan 1: Active Correction (Approaching Floor)

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Institutional quality — wealth-grade |
| Descriptive | Average Volume | Over 500K | Liquidity — ADV gate |
| Descriptive | Country | USA | LSE names → use TradingView |
| Technical | 200-Day SMA | Price above SMA200 | Floor intact — not broken |
| Technical | 50-Day SMA | Price below SMA50 | Pulled back from recent highs |
| Technical | Performance | Quarter -15% to -5% | Meaningful correction toward floor — targets the MSFT/CVS pattern |
| Technical | Beta | Under 1.5 | Wealth profile = lower volatility |

### Scan 2: Floor Contact (Closest to PASS)

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Institutional quality |
| Descriptive | Average Volume | Over 500K | Liquidity |
| Descriptive | Country | USA | LSE names → use TradingView |
| Technical | 200-Day SMA | Price above SMA200 | Floor intact |
| Technical | Performance 2 | Half -20% to -10% | Deep correction — price approaching SMA 200 |
| Technical | Beta | Under 1.5 | Wealth character |

**Post-Finviz:** Run as `--profile=WEALTH --mode=INFO`. Engine checks:
- Weekly 200-SMA floor integrity (not daily — Finviz uses daily 200-SMA ≈ 40-week SMA, which is *higher* than weekly 200-SMA for appreciating assets; expect some Finviz hits to fail Floor Proximity in engine)
- Floor_Prox_Pct < 15% (PE-CAL-1 §6.4 — widened from 8%)
- Extension: 1.0 ATR from SMA 200 (PE-CAL-1 §6.4 — anchor realigned from EMA 21 to SMA 200)
- Window: 4 weekly bars (PE-CAL-1 §6.5 — widened from 2)
- Counter-cyclical DI exemption: within 5% of SMA 200 + positive ADX slope (PE-CAL-1 §6.6 — allows entry during expected bearish pressure at structural floor)

**Key insight from testing:** MSFT was one bar from Profile C PASS (Floor_Prox 4.5%, every gate green except window). CVS was closest overall (Floor_Prox 8.06%, three gates barely failing). BLK, NEE, AVGO, V all 17-105% above SMA 200 — need significant corrections. Profile C entries are generational buying opportunities, not routine trades.

---

## STRUCTURAL RECLAIM SCAN (REL/IE-type setups)

**What we're looking for:** Stocks that have broken below the 50-SMA and are stabilising or beginning to recover. Watch for Floor_Failure_Reclaim progression.

| Tab | Filter | Setting | Rationale |
|-----|--------|---------|-----------|
| Descriptive | Market Cap | +Large (over $10bln) | Avoids junk |
| Descriptive | Average Volume | Over 500K | Liquidity |
| Technical | 50-Day SMA | Price below SMA50 | Currently broken — below floor |
| Technical | 200-Day SMA | Price above SMA200 | Not in full structural collapse (filters out REL.L / PYPL type breakdowns) |
| Technical | Performance | Week 0% or more | Stabilising or bouncing — recovery beginning |
| Technical | 52-Week High/Low | 20-30% below high | Significant correction, not a falling knife |
| Technical | Beta | Under 2.0 | Not excessively volatile |

**Post-Finviz:** Run as `--profile=TREND --mode=INFO`. Watch for:
- Floor_Failure_Reclaim progressing 1/3 → 2/3 → 3/3
- ADX approaching 20 (window reset on cross — PE-CAL-1 §6.3)
- Vol_Confirm_Ratio improving (distribution → mixed → institutional)
- Only enter after full reclaim (3/3) + Engine State upgrade to RESOLVING or TRENDING

**Key lesson from testing:** IE showed 1/3 reclaim with ADX ACCELERATING toward 20 and Distribution Warning on volume. Engine correctly held HALT. The reclaim mechanism gives damaged assets a path back to PASS without premature re-entry.

---

## LSE / NON-US MARKETS

**Half the active watchlist is London-listed** (PAF.L, GLEN.L, REL.L, IE). Finviz covers US markets only.

**For LSE stocks, use TradingView Screener** (tradingview.com/screener):
- Equivalent SMA filters available (SMA 50, SMA 200, EMA 8, EMA 21)
- Set Exchange to "LSE"
- ADX filter available under Technicals
- Volume filters available
- Weekly timeframe selectable for Profile C screening

**For dual-listed stocks** (BHP, CRH): Screen via Finviz using US ticker, run engine with either ticker.

---

## QUICK REFERENCE: ENGINE COMMANDS

```bash
# Standard scan
ibkr_purity_engine.py --ticker=XXXX --profile=SWING  --mode=INFO
ibkr_purity_engine.py --ticker=XXXX --profile=TREND  --mode=INFO
ibkr_purity_engine.py --ticker=XXXX --profile=WEALTH --mode=INFO

# Live mode (requires IB Gateway connection)
ibkr_purity_engine.py --ticker=XXXX --profile=SWING  --mode=LIVE
ibkr_purity_engine.py --ticker=XXXX --profile=TREND  --mode=LIVE
ibkr_purity_engine.py --ticker=XXXX --profile=WEALTH --mode=LIVE
```

---

## WORKFLOW

1. **Classify** — Know the asset's convexity class (C-1 to C-4) before scanning
2. **Screen** — Run appropriate Finviz/TradingView scan (weekly cadence for C, daily for A/B)
3. **Route** — Consult routing table: classification determines profile
4. **Audit** — Feed into engine for full TBS gate chain evaluation
5. **PASS** → Evaluate position sizing via Governor (Doc 3)
6. **HALT** → Note reason, add to watchlist, re-scan next period
7. **Near-PASS** → Monitor specific gates (e.g., CCJ: one close from PASS; MSFT: one pullback bar from PASS)

---

## PE-CAL-1 CHANGE LOG (Affecting Screener Parameters)

| Change | Old | New | Impact on Screener |
|--------|-----|-----|-------------------|
| Profile B pullback zone | SMA 50 + 0.5 ATR | EMA 21 + 0.5 ATR | Wider performance filter needed — stocks 5-10% below highs now in zone |
| Profile B window reset | Pullback/Breakout only | + ADX cross above 20 | Reclaim scan benefits — ADX approaching 20 is a leading indicator |
| Profile C floor proximity | 8% | 15% | More candidates pass initial screen |
| Profile C extension anchor | EMA 21 (0.5 ATR) | SMA 200 (1.0 ATR) | Both gates now concentric — Finviz SMA 200 filter more directly useful |
| Profile C window | 2 weekly bars | 4 weekly bars | Slower-developing pullbacks now viable |
| Profile C DI exemption | None | Within 5% of SMA 200 + ADX slope positive | Counter-cyclical entries possible — don't filter out -DI dominant names near SMA 200 |

---

*Document version: v2.0 — PE-CAL-1 calibration update*
*Previous version: v1.0 (pre-calibration)*
*Engine version: TBS v8.3 + PE-CAL-1 amendments*

# TBS Automated Trading Pipeline — Operator Reference

**Version:** v8.4 (Convexity-Aware)
**Engine:** ibkr_purity_engine.py v8.6 + Convexity Option B
**Last Updated:** March 2026

---

## Architecture Overview

The TBS pipeline is a layered system that gates trade entries through macro, fundamental, sector, and technical checks before sizing and execution. Every layer produces a PASS/HALT verdict. In entry mode, the first HALT kills the pipeline. In position monitor mode, all layers run to completion and verdicts accumulate.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     tbs_scanner.py (Batch Discovery)                 │
│  Reads watchlists → resolves convexity metadata → admissibility gate │
│  Iterates tickers through Step 6 ONLY → summary table of candidates  │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ per CANDIDATE (operator-driven)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     tbs_orchestrator.py (Full Pipeline)               │
│                                                                      │
│  Step 1: ibkr_sentinel.py         — Macro regime (SPY/TNX/VIX)      │
│  Step 2: Portfolio Governor        — Heat check (LIVE only)          │
│  Step 4b: ibkr_sympathy_audit.py  — Sector ETF floor                │
│  Step 4c: ibkr_asset_gates.py     — IV Guard + Dividend Lockout     │
│  Step 5: yahoo_fundamentals.py    — Clean Trade (ROIC/Rev/EPS/D:E)  │
│  Step 6: ibkr_purity_engine.py    — Technical Purity (15+ gates)    │
│  Step 3: Visual Proof              — Deferred to after Step 6 (LIVE) │
│  Step 7: Sizing                    — Governor risk model             │
│  Step 8: Bracket Order             — IBKR execution (LIVE only)      │
└──────────────────────────────────────────────────────────────────────┘
```

**Workflow:** The scanner identifies Step 6 PASS candidates from a watchlist. The operator then runs each candidate individually through the orchestrator for the full 8-step pipeline with LIVE sign-offs. This separation exists because the scanner's job is discovery (technical fitness only), while the orchestrator's job is execution gating (macro + fundamentals + technicals + sizing).

**Port Routing:** INFO mode (default) routes to IBKR Paper port 4002. LIVE mode routes to IBKR Live port 4001. This prevents accidental capital deployment during research.

---

## Prerequisites

All scripts require an active IB Gateway or TWS connection.

```bash
pip install ib_insync pandas pandas_ta yfinance plotly kaleido
```

---

## Profiles

Every command accepts `--profile` which determines the timeframe and gate parameters:

| Profile | Alias | Timeframe | Floor | Target Assets |
|---------|-------|-----------|-------|---------------|
| SWING | A | Hourly bars, 3-month history | VWAP | C-1 large-caps, session mean-reversion |
| TREND | B | Daily bars, 2-year history | SMA 50 | C-2/C-3 names in uptrends |
| WEALTH | C | Weekly bars, 10-year history | SMA 200 | C-1 quality compounders, generational entries |

---

## Convexity Classification

Assets are classified into four tiers that determine post-entry management regime:

| Class | Volatility | Risk | Management Regime | Admissible Profiles |
|-------|-----------|------|-------------------|---------------------|
| C-1 | Low | Low | Fixed floor, fixed targets | A ✓  B ✓  C ✓ |
| C-2 | Low–Moderate | Low–Moderate | Bounded, fixed targets, TQ Override eligible | A (restricted)  B ✓  C ✓ |
| C-3 | High | Moderate (bounded) | Trailing EMA 8 floor, open-ended reward | A ✗  B (restricted)  C ✗ |
| C-4 | Extreme | High | Excluded from TBS — future Protocol D | A ✗  B ✗  C ✗ |

Classification is operator-declared (via the Classification Prompt) and stored in metadata files. The engine does not infer convexity from price behaviour.

### Classification Storage

**Simple format** — `classifications.json` at project root:
```json
{
    "AAPL": "C2",
    "TSLA": "C3",
    "COST": "C1"
}
```

**Rich format** — companion `watchlists/tech.meta.json` alongside `watchlists/tech.txt`:
```json
{
    "NVDA": {
        "convexity": "C3",
        "role": "C",
        "admissibility": {
            "PROFILE_A": "not_permitted",
            "PROFILE_B": "restricted",
            "PROFILE_C": "not_permitted"
        },
        "confidence": "High"
    }
}
```

The companion format takes precedence when both exist.

### Inline Watchlist Format

Watchlist files support optional inline metadata:
```
# watchlists/tech.txt
AAPL                   # No classification → defaults to C-1
AAPL:C2:B              # Convexity-2, Role B (Growth Compounder)
NVDA:C3:C              # Convexity-3, Role C (Asymmetric Optionality)
BT.A.L:C2:B:8.0        # Convexity-2, Role B, WACC override 8.0
BT.A.L:8.0             # Legacy format: ticker + WACC override (no classification)
```

---

## Script Reference

### 1. tbs_scanner.py — Batch Scanner (Layer 4)

Scans a watchlist or ticker list through the Technical Engine (Step 6 only) and produces a summary table of candidates. This is the primary daily discovery tool. It does NOT run macro, fundamentals, sympathy, or asset gates — those are the orchestrator's domain, run per-candidate after scanner identifies PASS tickers.

```
usage: tbs_scanner.py [-h] (--tickers TICKERS | --watchlist WATCHLIST)
                      [--profile {SWING,TREND,WEALTH,A,B,C}]
                      [--mode {INFO,LIVE}]
                      [--require-classification]
```

**Key flags:**

| Flag | Purpose |
|------|---------|
| `--tickers` | Comma-separated: `AAPL,MSFT` or `AAPL:C2:B,NVDA:C3:C` |
| `--watchlist` | File in `watchlists/` dir, e.g. `tech.txt` |
| `--profile` | SWING / TREND / WEALTH (or A / B / C) |
| `--mode` | INFO (paper port 4002, default) or LIVE (port 4001) |
| `--require-classification` | Reject tickers without convexity metadata (default: unclassified → C-1) |

**Examples:**

```bash
# Daily scan: engine-only, TREND profile
python tbs_scanner.py --watchlist tech.txt --profile TREND

# Inline tickers with convexity metadata
python tbs_scanner.py --tickers "AAPL:C2:B,NVDA:C3:C,TSLA:C3:C" --profile TREND

# Strict mode: reject any ticker without a classification
python tbs_scanner.py --watchlist tech.txt --profile TREND --require-classification

# WEALTH profile scan
python tbs_scanner.py --watchlist wealth.txt --profile WEALTH
```

**Summary table output:**

```
  [OK] CANDIDATES (2)  --  Step 6 cleared. Proceed to Visual Audit:
     AAPL         C2     TRENDING | EMA 21 Floor | R:R 2.4 | Full Unit
     NVDA         C3     RESOLVING | EMA 8 Trail | Risk 0.6 ATR | Conv. Full

  [ -- ] TECHNICAL HALTS (1)  --  Failed at Step 6:
     MSFT         C2     MID-RANGE: ADX 18.3 < 20 | Mandate: WAIT

  [ XX ] CVX REJECTED (1)  --  Admissibility gate blocked (no API calls):
     TSLA         C3     C-3 NOT PERMITTED (Profile A / SWING)

  Next: Run CANDIDATES individually through the orchestrator for full pipeline:
        python tbs_orchestrator.py --ticker XXXX --profile TREND --mode INFO
```

> **Design note (SC-10):** The scanner is engine-only by design. Running Steps 1–5 inside the scanner was redundant — macro regime is identical for every ticker in the batch, fundamentals are identical per ticker, and the operator re-runs the full pipeline through the orchestrator anyway for each candidate. Engine-only saves API budget and eliminates the redundant path. Fundamental override flags (`--moat`, `--roic`, `--rev`, etc.) live on the orchestrator, not the scanner.

---

### 2. tbs_orchestrator.py — Master Orchestrator (Layer 3)

Runs the full 8-step pipeline for a single ticker. This is what the scanner calls internally, but can be used directly for individual analysis.

```
usage: tbs_orchestrator.py [-h] --ticker TICKER
                           [--profile {SWING,TREND,WEALTH,A,B,C}]
                           [--mode {INFO,LIVE}]
                           [--bypass_macro]
                           [--convexity {C1,C2,C3}]
                           [--etf]
                           [--entry-price ENTRY_PRICE] [--shares SHARES]
                           [--capital CAPITAL]
                           [--wacc WACC] [--moat MOAT] [--roic ROIC]
                           [--rev REV] [--eps EPS] [--de DE]
                           [--fcf-yield FCF_YIELD] [--tnx TNX]
                           [--pivot-confirmed]
                           [--sector-etf SECTOR_ETF]
```

**Key flags (beyond scanner):**

| Flag | Purpose |
|------|---------|
| `--ticker` | Single ticker (required) |
| `--convexity` | C1 / C2 / C3 — overrides classifications.json |
| `--bypass_macro` | Continue past macro HALTs (INFO mode only) |
| `--etf` | Force ETF classification (engine auto-detects, this overrides) |
| `--entry-price` + `--shares` | Enable Position Monitor mode (paired, both required) |
| `--capital` | Portfolio net worth override for sizing (enables sizing preview in INFO mode) |
| `--sector-etf` | Manual sector ETF for sympathy audit (e.g. XLE, XLK) |

**Examples:**

```bash
# Standard single-ticker analysis
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode INFO

# With convexity classification
python tbs_orchestrator.py --ticker TSLA --profile TREND --convexity C3

# Position monitoring (already holding 50 shares at $180)
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode INFO \
    --entry-price 180.00 --shares 50

# Sizing preview (INFO mode with capital override)
python tbs_orchestrator.py --ticker NVDA --profile TREND --mode INFO \
    --capital 100000 --convexity C2

# LIVE execution (full 8-step pipeline with human sign-offs)
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode LIVE \
    --moat WIDE --tnx 4.03

# LSE stock with WACC override
python tbs_orchestrator.py --ticker BT.A.L --profile WEALTH --wacc 9.2 --moat WIDE
```

**Position Monitor output** produces a three-state recommendation:

| State | Meaning | Action |
|-------|---------|--------|
| EXIT | Exit_Signal active (structural health deteriorating) | Evaluate immediate exit |
| NO ACTION | Environment blocks adds but position intact | Hold, do not add |
| FIT FOR ADD | All steps clear, no exit signals | Falls through to sizing (Steps 7–8) |

---

### 3. ibkr_purity_engine.py — Technical Purity Engine (Layer 2)

The core technical analysis engine. Evaluates 15+ structural gates and produces PASS/HALT with full diagnostic metrics. Can be run standalone for quick technical checks.

```
usage: ibkr_purity_engine.py [-h] --ticker TICKER
                             [--profile PROFILE]
                             [--mode MODE]
                             [--etf]
                             [--convexity {C1,C2,C3}]
```

**Examples:**

```bash
# Basic technical check
python ibkr_purity_engine.py --ticker AAPL --profile TREND --mode INFO

# C-3 asset (enables EMA 8 EXIT escalation, Modifier D INFORMATIONAL, etc.)
python ibkr_purity_engine.py --ticker TSLA --profile TREND --convexity C3

# Profile A (hourly) quick scan
python ibkr_purity_engine.py --ticker SPY --profile SWING --mode INFO

# ETF with explicit flag
python ibkr_purity_engine.py --ticker QQQ --profile SWING --etf

# WEALTH profile (weekly bars)
python ibkr_purity_engine.py --ticker COST --profile WEALTH --mode INFO
```

**Output** is JSON with three fields:

```json
{
    "status": "PASS",
    "diagnostic": "TRENDING pullback confirmed | EMA 21 Floor | ...",
    "metrics": {
        "Engine_State": "TRENDING",
        "Price": 185.23,
        "Structural_Floor": 178.50,
        "Hard_Stop": 172.30,
        "ATR": 4.13,
        "Profit_Target": 195.00,
        "Reward_Risk": 2.4,
        "Convexity_Class": "C2",
        "Profit_Target_Role": "PRESCRIPTIVE",
        "Exit_Signal": false
    }
}
```

**Convexity-aware behaviour** (when `--convexity C3`):

| Change | Effect |
|--------|--------|
| Convexity_Class tag | Written to metrics payload |
| Modifier D (Inst_Churn) | Annotated as INFORMATIONAL (not actionable) |
| Profit_Target_Role | INFORMATIONAL (not PRESCRIPTIVE) |
| Profit_Target_Synthetic | SUPPRESSED (open-ended reward) |
| EMA 8 EXIT escalation | WARNING → EXIT for C-3 |
| Risk_Per_Unit | Computed as (price − EMA 8) / ATR |
| Expectancy Gate (R:R) | BYPASSED (reward side is structurally undefined) |

---

### 4. ibkr_sentinel.py — Macro Regime Engine (Layer 0)

Classifies the market macro environment using SPY, TNX (10-Year yield), and VIX. Produces a regime classification that gates downstream pipeline steps.

```
usage: ibkr_sentinel.py [-h]
                        [--profile {SWING,TREND,WEALTH,A,B,C}]
                        [--mode {LIVE,INFO}]
                        [--port PORT]
                        [--no-rth]
                        [--debug]
```

**Examples:**

```bash
# Standard macro check
python ibkr_sentinel.py --profile TREND --mode INFO

# Debug mode (expanded diagnostics)
python ibkr_sentinel.py --profile TREND --debug

# Explicit port override
python ibkr_sentinel.py --profile SWING --port 4002
```

**Regime classifications:**

| Regime | Verdict | Impact |
|--------|---------|--------|
| GREEN | PASS | All profiles cleared |
| YELLOW | PASS | PASS with caution |
| AMBIGUOUS | PASS (with buffer) | Near SMA 50 boundary |
| DEFENSIVE | PASS (Profile A only) | Profile B/C entries BLOCKED |
| RED_UNCONFIRMED | HALT | Awaiting confirmation bars |
| RED_CONFIRMED | HALT | Confirmed bear regime |
| BLACK | HALT + FORCE HARVEST | Yield acceleration + volatility expansion |

**Automated checks (7 per run):** SPY vs SMA 50, TNX vs SMA 50, Yield Acceleration, Storm Watch (VIX ≥ 25), Volatility Expansion, ATR Lag Dampener, BLACK regime override.

---

### 5. yahoo_fundamentals.py — Clean Trade Audit (Layer 1)

Fundamental quality gate using Yahoo Finance data. Profile-specific thresholds.

```
usage: yahoo_fundamentals.py [-h] --ticker TICKER
                             [--profile {SWING,TREND,WEALTH,A,B,C}]
                             [--etf]
                             [--roic ROIC] [--rev REV] [--eps EPS]
                             [--de DE] [--fcf-yield FCF_YIELD]
                             [--wacc WACC] [--moat {WIDE,NARROW}]
                             [--tnx TNX]
                             [--pivot-confirmed]
```

**Examples:**

```bash
# Standard fundamental check
python yahoo_fundamentals.py --ticker AAPL --profile TREND

# WEALTH with full overrides
python yahoo_fundamentals.py --ticker COST --profile WEALTH \
    --moat WIDE --roic 25.0 --tnx 4.03

# With analyst-retrieved overrides (when Yahoo returns None)
python yahoo_fundamentals.py --ticker GLEN.L --profile TREND \
    --rev 8.5 --eps 12.3 --roic 18.0 --de 45.0

# Turnaround candidate
python yahoo_fundamentals.py --ticker CCJ --profile TREND \
    --pivot-confirmed --wacc 9.2
```

**Profile gates:**

| Profile | Requirements |
|---------|-------------|
| SWING (A) | Fundamentals bypassed — technical focus only |
| TREND (B) | Rev Growth > 0%, EPS Growth > 0% |
| WEALTH (C) | ROIC > 10%, Rev > 0%, EPS > 0%, Moat WIDE/NARROW, D/E reported, FCF vs TNX |
| ETF | All fundamental gates bypassed |

**Turnaround Patch** (all three required): Rev > 20% + ROIC > WACC + `--pivot-confirmed`.

---

### 6. ibkr_sympathy_audit.py — Sector Sympathy (Layer 1.5a)

Verifies the asset's sector ETF is above its structural floor. Prevents buying into sector-wide weakness.

```
usage: ibkr_sympathy_audit.py [-h] --ticker TICKER
                              [--profile {SWING,TREND,WEALTH,A,B,C}]
                              [--mode {INFO,LIVE}]
                              [--sector-etf SECTOR_ETF]
```

**Examples:**

```bash
# Auto-detect sector ETF via IBKR GICS classification
python ibkr_sympathy_audit.py --ticker AAPL --profile TREND

# Manual sector ETF override (when auto-detect fails)
python ibkr_sympathy_audit.py --ticker IE --profile TREND --sector-etf XLB
```

**Floor by profile:** SWING → VWAP, TREND → Daily SMA 50, WEALTH → Weekly SMA 200.

Broad index ETFs (SPY, QQQ, etc.) are auto-exempt — they ARE the market.

---

### 7. ibkr_asset_gates.py — Asset Permission (Layer 1.5b)

Per-ticker checks for IV Guard (limit order mandate) and Dividend Lockout.

```
usage: ibkr_asset_gates.py [-h] --ticker TICKER
                           [--profile {SWING,TREND,WEALTH,A,B,C}]
                           [--mode {INFO,LIVE}]
```

**Examples:**

```bash
python ibkr_asset_gates.py --ticker TNK --profile SWING
python ibkr_asset_gates.py --ticker MSFT --profile TREND --mode LIVE
```

**Output statuses:** PASS, LIMIT_ONLY (IV Guard triggered), BLOCKED (dividend lockout), ERROR.

---

## Common Workflows

### Daily Research Scan

```bash
# 1. Run macro check (once — applies to all tickers)
python ibkr_sentinel.py --profile TREND --mode INFO

# 2. Batch scan the watchlist (engine-only: Step 6 technical fitness)
python tbs_scanner.py --watchlist tech.txt --profile TREND

# 3. Full pipeline for each candidate (macro + fundamentals + technicals + sizing)
python tbs_orchestrator.py --ticker NVDA --profile TREND --mode INFO --convexity C2
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode INFO --convexity C2
```

### Position Monitoring

```bash
# Check health of held position
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode INFO \
    --entry-price 178.50 --shares 100 --capital 50000

# Monitor C-3 position
python tbs_orchestrator.py --ticker TSLA --profile TREND --convexity C3 \
    --entry-price 245.00 --shares 30
```

### LIVE Execution

```bash
# Full pipeline with human sign-offs at every gate
python tbs_orchestrator.py --ticker AAPL --profile TREND --mode LIVE \
    --capital 50000 --convexity C2
```

### Quick Technical Check

```bash
# Standalone engine for fast structural assessment
python ibkr_purity_engine.py --ticker NVDA --profile TREND --convexity C3
```

---

## Watchlist File Format

Place watchlist files in the `watchlists/` directory at the project root.

```
# watchlists/tech.txt
# Lines starting with # are comments
AAPL
MSFT
NVDA:C3:C
BT.A.L:8.0
COST:C1:A
```

Optional companion metadata file (`watchlists/tech.meta.json`) provides rich classification data including per-profile admissibility. The companion file takes precedence over both inline format and `classifications.json`.

---

## Override Flag Quick Reference

When automated data retrieval returns None, scripts issue `HALT (ANALYST RETRIEVE)`. Retrieve the value from Morningstar, SEC filings, or macrotrends.net and re-run with the override flag.

| Data | Flag | Script | API Source | Manual Sources |
|------|------|--------|------------|----------------|
| ROIC | `--roic` | yahoo_fundamentals | yfinance (unreliable) | Morningstar, SEC |
| Revenue Growth | `--rev` | yahoo_fundamentals | yfinance | Morningstar, SEC |
| EPS Growth | `--eps` | yahoo_fundamentals | yfinance | Morningstar, SEC |
| Debt-to-Equity | `--de` | yahoo_fundamentals | yfinance | Morningstar, SEC |
| FCF Yield | `--fcf-yield` | yahoo_fundamentals | yfinance (computed) | Morningstar, SEC |
| WACC | `--wacc` | yahoo_fundamentals | Not available | Morningstar, GuruFocus |
| Moat Rating | `--moat` | yahoo_fundamentals | Not available | Morningstar |
| TNX Yield | `--tnx` | yahoo_fundamentals | sentinel output | IBKR sentinel |
| Pivot | `--pivot-confirmed` | yahoo_fundamentals | Not quantifiable | Earnings calls |
| Sector ETF | `--sector-etf` | orchestrator/sympathy | IBKR GICS auto-detect | Manual if auto fails |
| Convexity | `--convexity` | orchestrator/engine | classifications.json | Classification Prompt |
| Capital | `--capital` | orchestrator | IBKR NetLiquidation | Manual override |
| Entry Price | `--entry-price` | orchestrator | Operator-provided | Position Monitor |
| Shares | `--shares` | orchestrator | Operator-provided | Position Monitor |

In LIVE mode, the orchestrator prompts inline for missing fundamental values (up to 5 retries for cascading missing fields). In INFO mode, HALTs are immediate.

---

## Project Structure

```
project_root/
├── scripts/
│   ├── ibkr_sentinel.py          # Layer 0: Macro regime
│   ├── yahoo_fundamentals.py     # Layer 1: Fundamental gates
│   ├── ibkr_sympathy_audit.py    # Layer 1.5a: Sector sympathy
│   ├── ibkr_asset_gates.py       # Layer 1.5b: IV Guard + Dividends
│   ├── ibkr_purity_engine.py     # Layer 2: Technical purity (15+ gates)
│   ├── tbs_orchestrator.py       # Layer 3: Pipeline governor
│   └── tbs_scanner.py            # Layer 4: Batch scanner
├── watchlists/
│   ├── tech.txt                  # Plain-text ticker lists
│   ├── tech.meta.json            # Optional companion metadata
│   └── wealth.txt
├── charts/                       # Auto-generated technical charts
├── classifications.json          # Simple convexity classifications
└── docs/                         # TBS governance documents (Docs 1–9)
```

---

## Document Authority

| Document | Governs |
|----------|---------|
| Doc 2 (Core Strategy v8.6) | All technical gate thresholds and entry protocols |
| Doc 3 (Portfolio Governor) | Sizing, heat limits, liquidation waterfall |
| Doc 5 (Sentinel Strategy) | Macro regime rules, sympathy audit |
| Doc 6 (Clean Trade) | Fundamental gates, turnaround patch |
| Doc 7 (Daily Battle Card) | 8-step execution pipeline sequence |
| Doc 8 (Systemic Automation) | Script architecture, port routing, override mandate |
| Convexity Redesign Proposal v2 | C-1/C-2/C-3 management regimes |
| Scanner Integration Spec v2 | Watchlist metadata, admissibility gates |
| Engine Execution Map v1.2 | Gate ordering, convexity code insertion points |

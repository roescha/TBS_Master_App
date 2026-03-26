import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
import pandas_ta as ta
import asyncio

# TBS SYMPATHY AUDIT (Step 4b) v8.6.0
# Standalone pre-gate for the 8-Step Pipeline [DOC 5 SEC 3.1 / DOC 7 STEP 4]
# Verifies: Sector ETF closing ABOVE the Profile-dependent Structural Floor.
# Floor mapping: Profile A = VWAP, Profile B = Daily SMA 50, Profile C = Weekly SMA 200.
# GICS auto-detection via IBKR reqContractDetails metadata.
# CLI --sector-etf override always takes priority over auto-detection.
# v8.6.0:   SA-002 (Sector ETF Context Enrichment -- 3-layer informational metrics)
# v8.5.0:   MOD-H (Commodity Sympathy Layer 2 -- WARNING for commodity proxy ETF below floor)
# v8.4.0:   SA-001 (Mining subcategory routes to XME instead of XLB)
# v8.3.1:   SA-1 (ib_connection param for orchestrator reuse, avoids clientId collision)
#            SA-1 (docstring resolution priority corrected to match code)

# ==============================================================================
# SECTOR ETF AUTO-MAPPING  [MANDATE: DOC 5 SEC 3.1 / GICS STANDARD]
# Maps IBKR ContractDetails.category -> Sector ETF for Sympathy Audit.
# IBKR field: details[0].category (broad GICS sector classification).
# --sector-etf CLI override always takes priority over auto-detection.
# ==============================================================================

# Primary mapping: IBKR industry string (BROAD sector) -> Sector ETF ticker
# Keys are UPPERCASED for case-insensitive matching.
# This is the fallback -- category and subcategory overrides are checked first.
INDUSTRY_TO_SECTOR_ETF = {
    "TECHNOLOGY":              "XLK",
    "ENERGY":                  "XLE",
    "FINANCIAL":               "XLF",
    "HEALTHCARE":              "XLV",
    "INDUSTRIAL":              "XLI",
    "BASIC MATERIALS":         "XLB",
    "CONSUMER, CYCLICAL":      "XLY",
    "CONSUMER, NON-CYCLICAL":  "XLP",
    "COMMUNICATIONS":          "XLC",
    "UTILITIES":               "XLU",
    "REAL ESTATE":             "XLRE",
}

# Category-level overrides: IBKR category (SPECIFIC sub-sector).
# Checked SECOND (after subcategory) -- overrides industry mapping.
# Used when the broad industry maps to the wrong sector ETF.
# Keys are UPPERCASED for case-insensitive matching.
CATEGORY_TO_SECTOR_ETF = {
    # --- Overrides (category maps to different ETF than broad industry) ---
    "AIRLINES":                "XLI",     # IBKR: Consumer,Cyclical -> should be Industrials
    "AEROSPACE/DEFENSE":       "XLI",     # IBKR: Industrial (correct but explicit)
    "BIOTECHNOLOGY":           "XBI",     # IBKR: Healthcare -> more specific biotech ETF
    "PHARMACEUTICALS":         "XLV",     # IBKR: Consumer,Non-cyclical -> should be Healthcare
    "HEALTHCARE-PRODUCTS":     "XLV",     # IBKR: Consumer,Non-cyclical -> Healthcare
    "HEALTHCARE-SERVICES":     "XLV",     # IBKR: Consumer,Non-cyclical -> Healthcare
    "TELECOMMUNICATIONS":      "XLC",     # Reinforcement (industry "Communications" works too)
    "TRANSPORTATION":          "XLI",     # IBKR: may classify under Consumer,Cyclical
    # --- Reinforcement mappings (category confirms industry) ---
    "SOFTWARE":                "XLK",
    "SEMICONDUCTORS":          "XLK",
    "COMPUTERS":               "XLK",
    "INTERNET":                "XLC",
    "MEDIA":                   "XLC",
    "ADVERTISING":             "XLC",
    "MINING":                  "XLB",
    "CHEMICALS":               "XLB",
    "FOREST PRODUCTS&PAPER":   "XLB",
    "IRON/STEEL":              "XLB",
    "BANKS":                   "XLF",
    "INSURANCE":               "XLF",
    "DIVERSIFIED FINAN SERV":  "XLF",
    "SAVINGS & LOANS":         "XLF",
    "RETAIL":                  "XLY",
    "AUTO MANUFACTURERS":      "XLY",
    "AUTO PARTS&EQUIPMENT":    "XLY",
    "HOME BUILDERS":           "XLY",
    "LEISURE TIME":            "XLY",
    "TEXTILES":                "XLY",
    "FOOD":                    "XLP",
    "BEVERAGES":               "XLP",
    "COSMETICS/PERSONAL CARE": "XLP",
    "HOUSEHOLD PRODUCTS/WARES":"XLP",
    "AGRICULTURE":             "XLP",
    "ELECTRIC":                "XLU",
    "GAS":                     "XLU",     # Gas UTILITIES (category level, not subcategory)
    "WATER":                   "XLU",
    "REITS":                   "XLRE",
    "REAL ESTATE":             "XLRE",
    "BUILDING MATERIALS":      "XLI",
    "MACHINERY-DIVERSIFIED":   "XLI",
    "MACHINERY-CONSTR & MINING":"XLI",
    "ENGINEERING&CONSTRUCTION": "XLI",
    "ELECTRICAL COMPO&EQUIP":  "XLI",
    "ENVIRONMENTAL CONTROL":   "XLI",
    "HAND/MACHINE TOOLS":      "XLI",
    "DISTRIBUTION/WHOLESALE":  "XLI",
    "PACKAGING&CONTAINERS":    "XLI",
}

# Subcategory-level overrides: IBKR subcategory (MOST SPECIFIC).
# Checked FIRST -- highest priority. Used for edge cases where both
# industry and category map to the wrong ETF.
# Uses substring matching (key IN subcategory) for flexibility.
SUBCATEGORY_TO_SECTOR_ETF = {
    # --- Energy (XLE) ---
    "TRANSPORT-MARINE":        "XLE",     # Tankers (TNK) -- marine energy transport
    "OIL&GAS":                 "XLE",     # Oil & gas subcategories
    "OIL COMP":                "XLE",     # "Oil Comp-Integrated", "Oil Comp-Exploration"
    "OIL REFIN":               "XLE",     # "Oil Refining & Marketing"
    "NATURAL GAS":             "XLE",     # Natural gas distribution/production
    "PIPELINES":               "XLE",     # Pipeline operators
    "COAL":                    "XLE",     # Coal producers
    # --- Technology (XLK) overrides for IBKR "Communications" misclass ---
    "INTERNET APPLIC SFTWR":   "XLK",     # SHOP -- IBKR says Communications/Internet
    "ENTERPRISE SOFTWARE":     "XLK",     # SaaS platforms
    "DATA PROCESSING":         "XLK",     # Payment processors (MA, V variant subcats)
    "ELECTRONIC COMPO":        "XLK",     # Component manufacturers
    "COMPUTER":                "XLK",     # Broad computer hardware/services
    # --- Consumer Discretionary (XLY) overrides ---
    "E-COMMERCE":              "XLY",     # MELI -- IBKR says Communications/Internet
    "AUTO":                    "XLY",     # Automakers, auto parts
    "LODGING":                 "XLY",     # Hotels
    "CASINO":                  "XLY",     # Gaming/casinos
    "TOYS":                    "XLY",     # Toy manufacturers
    "APPAREL":                 "XLY",     # Clothing brands
    # --- Consumer Staples (XLP) overrides ---
    "PET FOOD":                "XLP",     # FRPT -- IBKR says Cyclical but pet food = staples
    "TOBACCO":                 "XLP",     # Tobacco companies
    "HOUSEHOLD PROD":          "XLP",     # Household products
    # --- Healthcare (XLV) overrides for "Consumer, Non-cyclical" misclass ---
    "MEDICAL":                 "XLV",     # Medical devices, drugs, instruments
    "HEALTH CARE":             "XLV",     # HMOs, health services
    "DIAGNOSTIC":              "XLV",     # Diagnostics & research
    # --- Biotech (XBI) override ---
    "BIOTECH":                 "XBI",     # More specific than XLV for biotech names
    # --- Mining (XME) override [SA-001] ---
    "METAL MINING":            "XME",     # Diversified/base-metal miners (BHP, RIO, VALE)
    "MINING":                  "XME",     # Broad mining subcategories -> XME not XLB
    # --- Real Estate (XLRE) ---
    "REITS":                   "XLRE",    # Any REIT subcategory
    "REAL ESTATE":             "XLRE",    # Real estate services
}

# ETF ticker exemptions: broad index ETFs that don't map to a single sector.
# Sympathy Audit is architecturally irrelevant for these -- they ARE the market.
# If the ticker itself is in this set, sympathy is auto-skipped.
ETF_SYMPATHY_EXEMPT = {
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VT",    # US broad index
    "VUAG", "VWRP", "VWRL", "VUSA", "CSPX",              # LSE broad index
    "SCHD", "VIG", "DGRO",                                 # Dividend ETFs
    "XLE", "XLK", "XLF", "XLV", "XLI", "XLY", "XLP",     # Sector ETFs themselves
    "XLB", "XLC", "XLU", "XLRE", "XBI", "XME", "IBB",
}


# ==============================================================================
# COMMODITY PROXY MAP  [MOD-H: Layer 2 -- Commodity Sympathy]
# Maps ticker -> commodity proxy ETF for Layer 2 floor check.
# Only tickers listed here trigger Layer 2; all others skip silently.
# Source of truth is classifications.json commodity_proxy field -- this dict
# mirrors it in-process for O(1) lookup without re-parsing the file at runtime.
# ==============================================================================

COMMODITY_PROXY_MAP = {
    # Gold (GLD)
    "PAF":   "GLD",   # PAF.L (suffix stripped at runtime)
    "AU":    "GLD",
    "HOC":   "GLD",   # HOC.L
    # Silver (SLV)
    "VZLA":  "SLV",
    # Copper (COPX)
    "FCX":   "COPX",
    "ANTO":  "COPX",  # ANTO.L
    # Uranium (URA)
    "CCJ":   "URA",
    "NXE":   "URA",
    "UEC":   "URA",
    "DNN":   "URA",
    "UUUU":  "URA",
    "BWXT":  "URA",
    "LEU":   "URA",
    # Steel (SLX)
    "NUE":   "SLX",
    "CLF":   "SLX",
}




# ==============================================================================
# NICHE ETF MAP  [SA-002: Layer 3 -- Sub-Sector Niche ETF Context]
# Maps IBKR category/subcategory string -> sub-sector niche ETF ticker.
# Primary lookup by category/subcategory. Fallback by ticker (NICHE_ETF_TICKER_MAP).
# All niche ETFs are US-listed: Stock(ticker, "ARCA", "USD").
# ==============================================================================

NICHE_ETF_MAP = {
    # Semiconductors -> SMH (Sector: XLK)
    "SEMICONDUCTORS":              "SMH",
    "ELECTRONIC COMPO":            "SMH",
    # Software (SaaS) -> IGV (Sector: XLK)
    "SOFTWARE":                    "IGV",
    "ENTERPRISE SOFTWARE":         "IGV",
    "INTERNET APPLIC SFTWR":       "IGV",
    # Biotechnology -> IBB (Sector: XBI/XLV)
    "BIOTECHNOLOGY":               "IBB",
    "BIOTECH":                     "IBB",
    # Regional Banks -> KRE (Sector: XLF)
    "BANKS":                       "KRE",
    "SAVINGS & LOANS":             "KRE",
    # Homebuilding -> ITB (Sector: XLY)
    "HOME BUILDERS":               "ITB",
    # Retail -> XRT (Sector: XLY)
    "RETAIL":                      "XRT",
    # Aerospace & Defense -> ITA (Sector: XLI)
    "AEROSPACE/DEFENSE":           "ITA",
    # Infrastructure -> PAVE (Sector: XLI)
    "BUILDING MATERIALS":          "PAVE",
    "ENGINEERING&CONSTRUCTION":    "PAVE",
    "MACHINERY-DIVERSIFIED":       "PAVE",
    # Transportation -> IYT (Sector: XLI/XLE)
    "TRANSPORTATION":              "IYT",
    "TRANSPORT-MARINE":            "IYT",
    # Oil & Gas E&P -> XOP (Sector: XLE)
    "OIL&GAS":                     "XOP",
    "OIL COMP":                    "XOP",
    "OIL REFIN":                   "XOP",
    # Gold Mining -> GDX (overlap with COMMODITY_PROXY_MAP)
    "METAL MINING":                "GDX",
    # Fintech/Payments -> IPAY (Sector: XLK)
    "DATA PROCESSING":             "IPAY",
}

# Ticker-level fallback for niche ETFs with no clean IBKR category mapping.
# Checked only when NICHE_ETF_MAP produces no match. Keep minimal.
NICHE_ETF_TICKER_MAP = {
    # Cybersecurity -> HACK (Sector: XLK)
    "CRWD": "HACK", "PANW": "HACK", "FTNT": "HACK", "ZS": "HACK", "S": "HACK",
    # Solar Energy -> TAN (Sector: XLE/XLI)
    "ENPH": "TAN", "SEDG": "TAN", "FSLR": "TAN", "RUN": "TAN", "NOVA": "TAN",
    # Lithium & Batteries -> LIT (Cross-sector)
    "ALB": "LIT", "SQM": "LIT", "LTHM": "LIT", "LAC": "LIT",
}

# ==============================================================================
# SA-002 HELPER FUNCTIONS
# ==============================================================================

def _sa002_trend_label(change_20):
    """Derive trend label from 20-bar % change per DQ-1."""
    if change_20 is None:
        return "INSUFFICIENT DATA"
    if change_20 > 1.0:
        return "RISING"
    elif change_20 < -1.0:
        return "DECLINING"
    else:
        return "FLAT"


def _sa002_pct_change(df, n):
    """Compute % change over n bars from a DataFrame with 'close' column.
    Returns None if insufficient data."""
    if df is None or len(df) < n + 1:
        return None
    close_current = df['close'].iloc[-1]
    close_nbar = df['close'].iloc[-(n + 1)]
    if close_nbar == 0:
        return None
    return (close_current - close_nbar) / close_nbar * 100.0


def _sa002_compute_rs(numerator_change, benchmark_change):
    """Compute RS ratio or spread with negative benchmark guard (DQ-3).

    Ratio mode only works when both numerator and benchmark move in the same
    positive direction. When the benchmark is negative or near-zero, ratio
    semantics break:
      +12% / -6% = -2.0 (looks "underperforming" but numerator is up, benchmark down)
      -3% / -6% = 0.5   (looks "lagging" but numerator declined LESS = outperforming)
    In these cases, spread (percentage-point difference) preserves correct ordering.

    Returns: (rs_value, rs_label, spread_mode)
      rs_value: float ratio or spread value
      rs_label: LEADING / INLINE / LAGGING
      spread_mode: True if spread was used
    """
    if numerator_change is None or benchmark_change is None:
        return None, "UNAVAILABLE", False

    # Spread mode: used when ratio would be mathematically misleading.
    # Ratio is ONLY valid when both numerator and benchmark are positive and
    # benchmark is large enough (>= 0.1%). Every other combination produces
    # a number that either inverts ranking or has no ordinal meaning:
    #   +12% / -6%  = -2.0  (divergent: looks bad, actually outperforming)
    #   -3%  / -6%  = 0.5   (both down: looks lagging, actually less decline)
    #   -1%  / +0.3% = -3.3 (number is meaningless as a "ratio")
    #   +2%  / +0.05% = 40  (denominator noise amplified)
    use_ratio = (
        numerator_change >= 0
        and benchmark_change >= 0.1
    )

    if use_ratio:
        ratio = numerator_change / benchmark_change
        if ratio > 1.2:
            label = "LEADING"
        elif ratio < 0.8:
            label = "LAGGING"
        else:
            label = "INLINE"
        return round(ratio, 2), label, False
    else:
        # Spread mode: percentage-point difference
        spread = numerator_change - benchmark_change
        if spread > 2.0:
            label = "LEADING"
        elif spread < -2.0:
            label = "LAGGING"
        else:
            label = "INLINE"
        return round(spread, 2), label, True


def _sa002_golden_cross(df):
    """Compute SMA 50 vs SMA 200 golden cross status.
    Returns True (golden cross), False (death cross), or None (insufficient data)."""
    if df is None or len(df) < 200:
        return None
    sma_50 = df['close'].rolling(50).mean().iloc[-1]
    sma_200 = df['close'].rolling(200).mean().iloc[-1]
    if pd.isna(sma_50) or pd.isna(sma_200):
        return None
    return bool(sma_50 > sma_200)


def _sa002_resolve_niche_etf(ibkr_category, ibkr_subcategory, clean_ticker):
    """Look up niche ETF: first by category/subcategory, then by ticker fallback.
    Returns niche ETF ticker string or None."""
    # Primary: category/subcategory substring match (same pattern as sector ETF)
    for source_str in [ibkr_subcategory, ibkr_category]:
        if source_str:
            source_upper = source_str.upper()
            for key, niche_etf in NICHE_ETF_MAP.items():
                if key in source_upper:
                    return niche_etf
    # Fallback: ticker-level lookup
    return NICHE_ETF_TICKER_MAP.get(clean_ticker)


def _sa002_session_change(df):
    """Compute today's session % change from hourly bars.
    Filters to today's date, returns (open_of_first_bar, close_of_last_bar, pct_change)
    or (None, None, None) if insufficient data."""
    if df is None or len(df) < 1:
        return None, None, None
    try:
        # Index is datetime -- filter to today's calendar date
        last_date = df.index[-1]
        if hasattr(last_date, 'date'):
            today = last_date.date()
        else:
            today = pd.Timestamp(last_date).date()
        today_bars = df[df.index.date == today] if hasattr(df.index, 'date') else df.iloc[-1:]
        if len(today_bars) < 1:
            return None, None, None
        session_open = float(today_bars['open'].iloc[0])
        session_close = float(today_bars['close'].iloc[-1])
        if session_open == 0:
            return session_open, session_close, None
        pct = (session_close - session_open) / session_open * 100.0
        return session_open, session_close, round(pct, 2)
    except Exception:
        return None, None, None


def _sa002_format_rs_diagnostic(label_prefix, rs_value, rs_label, spread_mode, unavailable_reason=None):
    """Format a single RS line for the diagnostic string.
    Examples:
      XLK vs SPY: 1.15 (LEADING)
      XLK vs SPY: +1.8pp spread (INLINE) [spread mode]
      XLK vs SPY: UNAVAILABLE [SPY fetch failed]
    """
    if unavailable_reason:
        return f"{label_prefix}: UNAVAILABLE [{unavailable_reason}]"
    if spread_mode:
        sign = "+" if rs_value >= 0 else ""
        return f"{label_prefix}: {sign}{rs_value}pp spread ({rs_label}) [spread mode]"
    else:
        return f"{label_prefix}: {rs_value} ({rs_label})"


# Module-level SPY data cache to avoid redundant fetches within one session.
# Reset on each new orchestrator run (module reload or explicit clear).
_spy_cache = {"bars": None, "bar_size": None, "duration": None}


def run_sympathy_audit(ticker, profile="TREND", sector_etf_override=None, mode="INFO", ib_connection=None,
                       asset_close_current=None, asset_close_20bar=None):
    """
    Standalone Sympathy Audit per Doc 5 Sec 3.1 / Doc 7 Step 4.

    Resolution priority:
      1. --sector-etf CLI override (operator always wins)
      2. IBKR subcategory-level auto-detection (most specific, substring match)
      3. IBKR category-level auto-detection (specific sub-sector, exact match)
      4. IBKR industry-level auto-detection (broadest sector, substring match)
      5. SKIP with diagnostic (unmapped -- operator must add mapping or use CLI)

    Args:
        ticker: Asset ticker (e.g. TNK, MSFT, GLEN.L)
        profile: SWING (A), TREND (B), WEALTH (C) -- determines floor type
        sector_etf_override: CLI --sector-etf value (highest priority)
        mode: INFO (paper port 4002) or LIVE (port 4001)
        ib_connection: Existing IB connection to reuse (avoids clientId collision
                       when called from orchestrator). If None, creates own connection.
        asset_close_current: [SA-002 DQ-4] Asset current close price from engine bar data.
                             Optional (default None). When None, asset-vs-sector RS and
                             asset-vs-market RS are set to UNAVAILABLE.
        asset_close_20bar: [SA-002 DQ-4] Asset close price 20 bars ago from engine bar data.
                           Optional (default None). When None, asset RS fields UNAVAILABLE.

    Returns: (status, diagnostic, metrics) tuple
      status:     "PASS" | "HALT" | "EXEMPT" | "SKIPPED" | "ERROR"
      diagnostic: Human-readable explanation
      metrics:    Dict with audit trail (includes SA-002 sector context metrics)
    """

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # [SA-1] Connection reuse: when called from orchestrator, ib_connection is the
    # orchestrator's existing IB session. Avoids clientId collision (orchestrator=100,
    # standalone sympathy=130+). Only create/disconnect our own connection when standalone.
    _own_connection = (ib_connection is None)

    if _own_connection:
        unique_client_id = 130 + (os.getpid() % 50)  # Range 130-179, avoids orchestrator(100)
        port = 4002 if mode.upper() == "INFO" else 4001
        ib = IB()
    else:
        ib = ib_connection

    metrics = {}

    # --- PROFILE VALIDATION ---
    VALID_PROFILES = {"SWING", "TREND", "WEALTH", "A", "B", "C"}
    if profile.upper() not in VALID_PROFILES:
        return "ERROR", f"INVALID PROFILE: '{profile}'.", {}

    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping[profile.upper()]

    # --- TICKER ROUTING ---
    clean_ticker = ticker.upper()
    exchange, currency, p_exchange = "SMART", "USD", ""
    routing_map = {
        '.L':  {'exchange': 'SMART', 'currency': 'GBP', 'primary': 'LSE'},
        '.TO': {'exchange': 'SMART', 'currency': 'CAD', 'primary': 'TSE'},
        '.DE': {'exchange': 'IBIS',  'currency': 'EUR', 'primary': 'IBIS'},
        '.AS': {'exchange': 'AEB',   'currency': 'EUR', 'primary': 'AEB'},
        '.PA': {'exchange': 'SBF',   'currency': 'EUR', 'primary': 'SBF'},
    }
    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exchange'], route['currency'], route['primary']
            break

    try:
        if _own_connection:
            ib.connect('127.0.0.1', port, clientId=unique_client_id)
            ib.reqMarketDataType(1)
        # --- ASSET IDENTIFICATION ---
        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)
        details = ib.reqContractDetails(contract)

        if not details:
            return "ERROR", f"No contract details found for '{clean_ticker}'.", metrics

        meta = details[0]
        ibkr_industry = getattr(meta, 'industry', '') or ''
        ibkr_category = getattr(meta, 'category', '') or ''
        ibkr_subcategory = getattr(meta, 'subcategory', '') or ''
        long_name = getattr(meta, 'longName', '') or ''

        metrics["Ticker"] = clean_ticker
        metrics["Long_Name"] = long_name
        metrics["Profile"] = f"{profile.upper()} ({p_code})"
        metrics["IBKR_Industry"] = ibkr_industry or "N/A"
        metrics["IBKR_Category"] = ibkr_category or "N/A"
        metrics["IBKR_Subcategory"] = ibkr_subcategory or "N/A"

        # --- ETF EXEMPTION CHECK ---
        if clean_ticker in ETF_SYMPATHY_EXEMPT:
            metrics["Sympathy_Status"] = "EXEMPT"
            metrics["Sector_ETF_Source"] = "ETF_SYMPATHY_EXEMPT"
            return (
                "EXEMPT",
                f"SYMPATHY AUDIT EXEMPT: '{clean_ticker}' is a broad index or sector ETF. "
                f"Sympathy check is architecturally irrelevant.",
                metrics
            )

        # --- SECTOR ETF RESOLUTION ---
        resolved_etf = None
        detect_source = None

        # Priority 1: CLI override
        if sector_etf_override is not None:
            resolved_etf = sector_etf_override.upper()
            detect_source = f"CLI_OVERRIDE: --sector-etf={resolved_etf}"

        # Priority 2: Subcategory override (most specific, substring match)
        if resolved_etf is None and ibkr_subcategory:
            sub_upper = ibkr_subcategory.upper()
            for key, etf in SUBCATEGORY_TO_SECTOR_ETF.items():
                if key in sub_upper:
                    resolved_etf = etf
                    detect_source = f"SUBCATEGORY: '{ibkr_subcategory}' -> {etf}"
                    break

        # Priority 3: Category override (specific sub-sector, exact match)
        if resolved_etf is None and ibkr_category:
            cat_upper = ibkr_category.upper().strip()
            if cat_upper in CATEGORY_TO_SECTOR_ETF:
                resolved_etf = CATEGORY_TO_SECTOR_ETF[cat_upper]
                detect_source = f"CATEGORY: '{ibkr_category}' -> {resolved_etf}"

        # Priority 4: Industry match (broad sector, substring match)
        if resolved_etf is None and ibkr_industry:
            for key, etf in INDUSTRY_TO_SECTOR_ETF.items():
                if key in ibkr_industry.upper():
                    resolved_etf = etf
                    detect_source = f"INDUSTRY: '{ibkr_industry}' -> {etf}"
                    break

        # Priority 5: No match -- skip with diagnostic
        if resolved_etf is None:
            metrics["Sympathy_Status"] = "SKIPPED"
            metrics["Sector_ETF_Source"] = "AUTO_DETECTION_FAILED"
            return (
                "SKIPPED",
                f"SYMPATHY AUDIT SKIPPED: auto-detection failed for "
                f"'{clean_ticker}' (industry='{ibkr_industry}', category='{ibkr_category}'). "
                f"Add mapping to INDUSTRY_TO_SECTOR_ETF or CATEGORY_TO_SECTOR_ETF, "
                f"or pass --sector-etf manually.",
                metrics
            )

        metrics["Sector_ETF"] = resolved_etf
        metrics["Sector_ETF_Source"] = detect_source

        # --- SECTOR ETF DATA FETCH ---
        sector_contract = Stock(resolved_etf, "SMART", "USD")
        sector_details = ib.reqContractDetails(sector_contract)
        if sector_details:
            sector_contract = sector_details[0].contract

        # Profile-dependent data fetch
        sector_tf_map = {
            "A": ("1 hour", "3 M"),    # VWAP needs intraday bars
            "B": ("1 day",  "1 Y"),    # SMA 50 needs ~60 daily bars
            "C": ("1 week", "5 Y"),    # SMA 200 needs ~220 weekly bars
        }
        s_res, s_dur = sector_tf_map[p_code]
        sector_bars = ib.reqHistoricalData(
            sector_contract, '', s_dur, s_res, 'TRADES', True
        )

        if not sector_bars or len(sector_bars) < 10:
            return "ERROR", (
                f"SYMPATHY AUDIT ERROR: insufficient data for sector ETF "
                f"'{resolved_etf}' ({len(sector_bars) if sector_bars else 0} bars)."
            ), metrics

        sector_df = util.df(sector_bars)
        sector_df.set_index('date', inplace=True)

        # --- COMPUTE PROFILE-DEPENDENT FLOOR ---
        if p_code == "A":
            sector_df.ta.vwap(append=True)
            s_vwap_cols = [c for c in sector_df.columns if 'VWAP' in c]
            if not s_vwap_cols:
                return "ERROR", f"VWAP computation failed for '{resolved_etf}'.", metrics
            sector_floor_raw = sector_df[s_vwap_cols[0]].iloc[-1]
            floor_label = "VWAP"
        elif p_code == "B":
            sector_df['SMA_50'] = sector_df['close'].rolling(50).mean()
            if pd.isna(sector_df['SMA_50'].iloc[-1]):
                return "ERROR", f"SMA 50 not available for '{resolved_etf}' (insufficient history).", metrics
            sector_floor_raw = sector_df['SMA_50'].iloc[-1]
            floor_label = "SMA_50"
        else:
            sector_df['SMA_200'] = sector_df['close'].rolling(200).mean()
            if pd.isna(sector_df['SMA_200'].iloc[-1]):
                return "ERROR", f"SMA 200 not available for '{resolved_etf}' (insufficient history).", metrics
            sector_floor_raw = sector_df['SMA_200'].iloc[-1]
            floor_label = "SMA_200"

        sector_close = sector_df['close'].iloc[-1]
        sector_floor_display = round(sector_floor_raw, 2)
        sector_close_display = round(sector_close, 2)

        metrics["Sympathy_Close"] = sector_close_display
        metrics["Sympathy_Floor"] = sector_floor_display
        metrics["Sympathy_Floor_Type"] = floor_label

        # --- VERDICT (Layer 1 decision -- SA-002 does NOT modify this) ---
        is_halt = (sector_close < sector_floor_raw)
        l2_commodity_diag = ""

        if is_halt:
            metrics["Sympathy_Status"] = "FAIL"
            l1_diag = (
                f"SYMPATHY AUDIT FAILED: Sector ETF '{resolved_etf}' "
                f"close ({sector_close_display}) is BELOW its Structural Floor "
                f"({floor_label} = {sector_floor_display}). "
                f"Asset '{clean_ticker}' is BLOCKED per Doc 5 Sec 3.1."
            )
        else:
            margin = round(sector_close - sector_floor_raw, 2)
            margin_pct = round((sector_close - sector_floor_raw) / sector_floor_raw * 100, 2)
            metrics["Sympathy_Status"] = "PASS"
            metrics["Sympathy_Margin"] = margin
            metrics["Sympathy_Margin_Pct"] = margin_pct

            # ------------------------------------------------------------------
            # LAYER 2: COMMODITY SYMPATHY CHECK  [MOD-H]
            # Runs only when ticker has a commodity_proxy entry.
            # Reuses the existing `ib` connection -- no second connection opened.
            # Result is ADDITIVE: Layer 1 verdict is preserved regardless.
            # ------------------------------------------------------------------
            proxy_etf = COMMODITY_PROXY_MAP.get(clean_ticker)
            if proxy_etf:
                try:
                    proxy_contract = Stock(proxy_etf, "SMART", "USD")
                    proxy_details = ib.reqContractDetails(proxy_contract)
                    if proxy_details:
                        proxy_contract = proxy_details[0].contract

                    proxy_bars = ib.reqHistoricalData(
                        proxy_contract, '', s_dur, s_res, 'TRADES', True
                    )

                    if proxy_bars and len(proxy_bars) >= 10:
                        proxy_df = util.df(proxy_bars)
                        proxy_df.set_index('date', inplace=True)

                        # Compute same floor type used in Layer 1 for this profile
                        if p_code == "A":
                            proxy_df.ta.vwap(append=True)
                            p_vwap_cols = [c for c in proxy_df.columns if 'VWAP' in c]
                            proxy_floor_raw = proxy_df[p_vwap_cols[0]].iloc[-1] if p_vwap_cols else None
                        elif p_code == "B":
                            proxy_df['SMA_50'] = proxy_df['close'].rolling(50).mean()
                            proxy_floor_raw = proxy_df['SMA_50'].iloc[-1]
                            proxy_floor_raw = None if pd.isna(proxy_floor_raw) else proxy_floor_raw
                        else:
                            proxy_df['SMA_200'] = proxy_df['close'].rolling(200).mean()
                            proxy_floor_raw = proxy_df['SMA_200'].iloc[-1]
                            proxy_floor_raw = None if pd.isna(proxy_floor_raw) else proxy_floor_raw

                        if proxy_floor_raw is not None:
                            proxy_close = proxy_df['close'].iloc[-1]
                            proxy_margin_pct = round(
                                (proxy_close - proxy_floor_raw) / proxy_floor_raw * 100, 2
                            )
                            proxy_status = "WARNING" if proxy_close < proxy_floor_raw else "PASS"

                            metrics["Commodity_Proxy_ETF"]         = proxy_etf
                            metrics["Commodity_Proxy_Close"]       = round(proxy_close, 2)
                            metrics["Commodity_Proxy_Floor"]       = round(proxy_floor_raw, 2)
                            metrics["Commodity_Proxy_Floor_Type"]  = floor_label
                            metrics["Commodity_Proxy_Status"]      = proxy_status
                            metrics["Commodity_Proxy_Margin_Pct"]  = proxy_margin_pct
                except Exception:
                    pass  # Layer 2 failures are non-fatal; Layer 1 verdict stands
            # ------------------------------------------------------------------
            # END LAYER 2 (MOD-H)
            # ------------------------------------------------------------------

            # Build Layer 1 + MOD-H diagnostic
            l1_diag = (
                f"SYMPATHY AUDIT PASSED: Sector ETF '{resolved_etf}' "
                f"close ({sector_close_display}) is ABOVE its Structural Floor "
                f"({floor_label} = {sector_floor_display}). "
                f"Margin: +{margin} ({margin_pct}%)."
            )
            if metrics.get("Commodity_Proxy_Status") == "WARNING":
                proxy_close_d  = metrics["Commodity_Proxy_Close"]
                proxy_floor_d  = metrics["Commodity_Proxy_Floor"]
                proxy_margin_d = metrics["Commodity_Proxy_Margin_Pct"]
                l2_commodity_diag = (
                    f" [MOD-H WARNING] Commodity proxy ETF '{metrics['Commodity_Proxy_ETF']}' "
                    f"close ({proxy_close_d}) is BELOW its {floor_label} floor "
                    f"({proxy_floor_d}). Margin: {proxy_margin_d}%. "
                    f"Layer 1 PASS preserved -- Operator review required."
                )
            elif metrics.get("Commodity_Proxy_Status") == "PASS":
                proxy_margin_d = metrics["Commodity_Proxy_Margin_Pct"]
                l2_commodity_diag = (
                    f" [MOD-H] Commodity proxy ETF '{metrics['Commodity_Proxy_ETF']}' "
                    f"ABOVE {floor_label} floor. Margin: +{proxy_margin_d}%."
                )

        # ==================================================================
        # SA-002: SECTOR CONTEXT ENRICHMENT (ALL PATHS -- PASS and HALT)
        # Informational metrics only. Layer 1 verdict is NEVER modified.
        # ==================================================================

        # ------------------------------------------------------------------
        # SA-002 LAYER 1: Sector ETF Context (no new IBKR calls)
        # ------------------------------------------------------------------
        sector_etf_name = None
        try:
            if sector_details:
                sector_etf_name = getattr(sector_details[0], 'longName', None)
        except Exception:
            pass
        metrics["Sector_ETF_Name"] = sector_etf_name

        sector_change_10 = _sa002_pct_change(sector_df, 10)
        sector_change_20 = _sa002_pct_change(sector_df, 20)
        sector_trend = _sa002_trend_label(sector_change_20)
        sector_golden_cross = _sa002_golden_cross(sector_df)

        metrics["Sector_ETF_Change_10"] = round(sector_change_10, 2) if sector_change_10 is not None else None
        metrics["Sector_ETF_Change_20"] = round(sector_change_20, 2) if sector_change_20 is not None else None
        metrics["Sector_ETF_Trend"] = sector_trend
        metrics["Sector_ETF_Golden_Cross"] = sector_golden_cross

        # ------------------------------------------------------------------
        # SA-002 LAYER 2: Multi-Layer Relative Strength
        # ------------------------------------------------------------------

        # -- Asset % change (from orchestrator params, DQ-4) --
        # Self-fetch fallback: when called standalone (CLI), the orchestrator
        # doesn't provide asset close prices. Fetch them here using the
        # already-open IB connection and the same bar size/duration as the sector ETF.
        if asset_close_current is None or asset_close_20bar is None:
            try:
                asset_bars = ib.reqHistoricalData(
                    contract, '', s_dur, s_res, 'TRADES', True
                )
                if asset_bars and len(asset_bars) >= 21:
                    _asset_df = util.df(asset_bars)
                    _asset_df.set_index('date', inplace=True)
                    asset_close_current = float(_asset_df['close'].iloc[-1])
                    asset_close_20bar = float(_asset_df['close'].iloc[-21])
            except Exception:
                _asset_df = None
        else:
            _asset_df = None  # orchestrator provided params; no asset bars fetched

        asset_change_20 = None
        if asset_close_current is not None and asset_close_20bar is not None:
            if asset_close_20bar != 0:
                asset_change_20 = (asset_close_current - asset_close_20bar) / asset_close_20bar * 100.0

        # -- Asset vs Sector RS --
        avs_unavailable_reason = None
        if asset_change_20 is None:
            avs_unavailable_reason = "asset close data not provided"
        if sector_change_20 is None and avs_unavailable_reason is None:
            avs_unavailable_reason = "sector data insufficient"

        if avs_unavailable_reason:
            metrics["Asset_vs_Sector_RS"] = None
            metrics["Asset_vs_Sector_RS_Label"] = "UNAVAILABLE"
            metrics["Asset_vs_Sector_RS_Spread_Mode"] = False
        else:
            avs_val, avs_label, avs_spread = _sa002_compute_rs(asset_change_20, sector_change_20)
            metrics["Asset_vs_Sector_RS"] = avs_val
            metrics["Asset_vs_Sector_RS_Label"] = avs_label
            metrics["Asset_vs_Sector_RS_Spread_Mode"] = avs_spread

        # -- SPY fetch (self-contained, DQ-5) --
        global _spy_cache
        spy_df = None
        spy_change_20 = None
        spy_fetch_failed = False

        try:
            if _spy_cache["bars"] is not None and _spy_cache["bar_size"] == s_res and _spy_cache["duration"] == s_dur:
                # Cache hit -- reuse SPY data from earlier call in same session
                spy_df = _spy_cache["bars"]
            else:
                spy_contract = Stock("SPY", "ARCA", "USD")
                spy_bars = ib.reqHistoricalData(
                    spy_contract, '', s_dur, s_res, 'TRADES', True
                )
                if spy_bars and len(spy_bars) >= 21:
                    spy_df = util.df(spy_bars)
                    spy_df.set_index('date', inplace=True)
                    _spy_cache = {"bars": spy_df, "bar_size": s_res, "duration": s_dur}
                else:
                    spy_fetch_failed = True
        except Exception:
            spy_fetch_failed = True

        if spy_df is not None:
            spy_change_20 = _sa002_pct_change(spy_df, 20)

        # -- Sector vs Market RS --
        svm_unavailable_reason = None
        if spy_fetch_failed or spy_change_20 is None:
            svm_unavailable_reason = "SPY fetch failed" if spy_fetch_failed else "SPY data insufficient"
        if sector_change_20 is None and svm_unavailable_reason is None:
            svm_unavailable_reason = "sector data insufficient"

        if svm_unavailable_reason:
            metrics["Sector_vs_Market_RS"] = None
            metrics["Sector_vs_Market_RS_Label"] = "UNAVAILABLE"
            metrics["Sector_vs_Market_RS_Spread_Mode"] = False
        else:
            svm_val, svm_label, svm_spread = _sa002_compute_rs(sector_change_20, spy_change_20)
            metrics["Sector_vs_Market_RS"] = svm_val
            metrics["Sector_vs_Market_RS_Label"] = svm_label
            metrics["Sector_vs_Market_RS_Spread_Mode"] = svm_spread

        # -- Asset vs Market RS --
        avm_unavailable_reason = None
        if asset_change_20 is None:
            avm_unavailable_reason = "asset close data not provided"
        elif spy_fetch_failed or spy_change_20 is None:
            avm_unavailable_reason = "SPY fetch failed" if spy_fetch_failed else "SPY data insufficient"

        if avm_unavailable_reason:
            metrics["Asset_vs_Market_RS"] = None
            metrics["Asset_vs_Market_RS_Label"] = "UNAVAILABLE"
            metrics["Asset_vs_Market_RS_Spread_Mode"] = False
        else:
            avm_val, avm_label, avm_spread = _sa002_compute_rs(asset_change_20, spy_change_20)
            metrics["Asset_vs_Market_RS"] = avm_val
            metrics["Asset_vs_Market_RS_Label"] = avm_label
            metrics["Asset_vs_Market_RS_Spread_Mode"] = avm_spread

        # ------------------------------------------------------------------
        # SA-002 LAYER 3: Sub-Sector Niche ETF Context (DQ-7: all paths)
        # ------------------------------------------------------------------
        niche_etf_ticker = _sa002_resolve_niche_etf(ibkr_category, ibkr_subcategory, clean_ticker)
        metrics["Niche_ETF"] = niche_etf_ticker
        metrics["Niche_ETF_Name"] = None
        metrics["Niche_ETF_Change_20"] = None
        metrics["Niche_ETF_Trend"] = None
        metrics["Niche_vs_Sector_RS"] = None
        metrics["Niche_vs_Sector_RS_Label"] = None
        metrics["Niche_vs_Sector_RS_Spread_Mode"] = False

        niche_diag_block = ""
        niche_fetch_failed = False

        if niche_etf_ticker:
            try:
                niche_contract = Stock(niche_etf_ticker, "ARCA", "USD")
                niche_details = ib.reqContractDetails(niche_contract)
                if niche_details:
                    niche_contract = niche_details[0].contract
                    metrics["Niche_ETF_Name"] = getattr(niche_details[0], 'longName', None)

                niche_bars = ib.reqHistoricalData(
                    niche_contract, '', s_dur, s_res, 'TRADES', True
                )

                if niche_bars and len(niche_bars) >= 21:
                    niche_df = util.df(niche_bars)
                    niche_df.set_index('date', inplace=True)

                    niche_change_20 = _sa002_pct_change(niche_df, 20)
                    metrics["Niche_ETF_Change_20"] = round(niche_change_20, 2) if niche_change_20 is not None else None
                    metrics["Niche_ETF_Trend"] = _sa002_trend_label(niche_change_20)

                    # Niche vs Sector RS (denominator = sector_change_20)
                    if niche_change_20 is not None and sector_change_20 is not None:
                        nvs_val, nvs_label, nvs_spread = _sa002_compute_rs(niche_change_20, sector_change_20)
                        metrics["Niche_vs_Sector_RS"] = nvs_val
                        metrics["Niche_vs_Sector_RS_Label"] = nvs_label
                        metrics["Niche_vs_Sector_RS_Spread_Mode"] = nvs_spread
                else:
                    niche_fetch_failed = True
            except Exception:
                niche_fetch_failed = True

            if niche_fetch_failed:
                metrics["Niche_ETF_Trend"] = "UNAVAILABLE"
                metrics["Niche_vs_Sector_RS_Label"] = "UNAVAILABLE"

        # ------------------------------------------------------------------
        # SA-002 SESSION RS: Today-only relative strength (Profile A only)
        # Uses hourly bars already in memory. Zero additional IBKR calls.
        # ------------------------------------------------------------------
        if p_code == "A":
            _, _, sess_sector_chg = _sa002_session_change(sector_df)
            _, _, sess_spy_chg = _sa002_session_change(spy_df)
            _, _, sess_asset_chg = _sa002_session_change(_asset_df)

            if sess_asset_chg is not None and sess_sector_chg is not None:
                s_avs_val, s_avs_label, s_avs_spread = _sa002_compute_rs(sess_asset_chg, sess_sector_chg)
                metrics["Session_Asset_vs_Sector_RS"] = s_avs_val
                metrics["Session_Asset_vs_Sector_RS_Label"] = s_avs_label
                metrics["Session_Asset_vs_Sector_RS_Spread_Mode"] = s_avs_spread
            else:
                metrics["Session_Asset_vs_Sector_RS"] = None
                metrics["Session_Asset_vs_Sector_RS_Label"] = "UNAVAILABLE"
                metrics["Session_Asset_vs_Sector_RS_Spread_Mode"] = False

            if sess_sector_chg is not None and sess_spy_chg is not None:
                s_svm_val, s_svm_label, s_svm_spread = _sa002_compute_rs(sess_sector_chg, sess_spy_chg)
                metrics["Session_Sector_vs_Market_RS"] = s_svm_val
                metrics["Session_Sector_vs_Market_RS_Label"] = s_svm_label
                metrics["Session_Sector_vs_Market_RS_Spread_Mode"] = s_svm_spread
            else:
                metrics["Session_Sector_vs_Market_RS"] = None
                metrics["Session_Sector_vs_Market_RS_Label"] = "UNAVAILABLE"
                metrics["Session_Sector_vs_Market_RS_Spread_Mode"] = False

            if sess_asset_chg is not None and sess_spy_chg is not None:
                s_avm_val, s_avm_label, s_avm_spread = _sa002_compute_rs(sess_asset_chg, sess_spy_chg)
                metrics["Session_Asset_vs_Market_RS"] = s_avm_val
                metrics["Session_Asset_vs_Market_RS_Label"] = s_avm_label
                metrics["Session_Asset_vs_Market_RS_Spread_Mode"] = s_avm_spread
            else:
                metrics["Session_Asset_vs_Market_RS"] = None
                metrics["Session_Asset_vs_Market_RS_Label"] = "UNAVAILABLE"
                metrics["Session_Asset_vs_Market_RS_Spread_Mode"] = False

            metrics["Session_Asset_Change"] = sess_asset_chg
            metrics["Session_Sector_Change"] = sess_sector_chg
            metrics["Session_SPY_Change"] = sess_spy_chg

        # ------------------------------------------------------------------
        # SA-002 DIAGNOSTIC STRING: [SECTOR CONTEXT] + [SUB-SECTOR]
        # Appended to existing diagnostic on ALL paths.
        # ------------------------------------------------------------------
        sc_parts = []

        # Sector ETF identity + trend
        name_str = f" ({sector_etf_name})" if sector_etf_name else ""
        if sector_change_20 is not None:
            sign = "+" if sector_change_20 >= 0 else ""
            sc_parts.append(f"{resolved_etf}{name_str} {sector_trend} {sign}{round(sector_change_20, 1)}% 20d")
        else:
            sc_parts.append(f"{resolved_etf}{name_str} {sector_trend}")

        # Golden Cross / Death Cross
        if sector_golden_cross is True:
            sc_parts[-1] += ", GOLDEN CROSS"
        elif sector_golden_cross is False:
            sc_parts[-1] += ", DEATH CROSS"

        # Sector vs Market RS
        sc_parts.append(
            _sa002_format_rs_diagnostic(
                f"{resolved_etf} vs SPY",
                metrics.get("Sector_vs_Market_RS"),
                metrics.get("Sector_vs_Market_RS_Label"),
                metrics.get("Sector_vs_Market_RS_Spread_Mode", False),
                svm_unavailable_reason
            )
        )

        # Asset vs Sector RS
        sc_parts.append(
            _sa002_format_rs_diagnostic(
                f"{clean_ticker} vs {resolved_etf}",
                metrics.get("Asset_vs_Sector_RS"),
                metrics.get("Asset_vs_Sector_RS_Label"),
                metrics.get("Asset_vs_Sector_RS_Spread_Mode", False),
                avs_unavailable_reason
            )
        )

        # Asset vs Market RS
        sc_parts.append(
            _sa002_format_rs_diagnostic(
                f"{clean_ticker} vs SPY",
                metrics.get("Asset_vs_Market_RS"),
                metrics.get("Asset_vs_Market_RS_Label"),
                metrics.get("Asset_vs_Market_RS_Spread_Mode", False),
                avm_unavailable_reason
            )
        )

        sector_context_diag = " [SECTOR CONTEXT] " + ". ".join(sc_parts) + "."

        # [SUB-SECTOR] block (only when niche mapping exists)
        if niche_etf_ticker:
            if niche_fetch_failed:
                niche_diag_block = (
                    f" [SUB-SECTOR] {niche_etf_ticker} fetch failed -- context unavailable."
                )
            else:
                niche_name_str = f" ({metrics.get('Niche_ETF_Name', '')})" if metrics.get('Niche_ETF_Name') else ""
                niche_change = metrics.get("Niche_ETF_Change_20")
                niche_trend = metrics.get("Niche_ETF_Trend", "UNAVAILABLE")
                if niche_change is not None:
                    niche_sign = "+" if niche_change >= 0 else ""
                    niche_trend_str = f"{niche_etf_ticker}{niche_name_str} {niche_trend} {niche_sign}{niche_change}% 20d"
                else:
                    niche_trend_str = f"{niche_etf_ticker}{niche_name_str} {niche_trend}"

                # Niche vs Sector RS
                nvs_rs_str = ""
                if metrics.get("Niche_vs_Sector_RS") is not None:
                    nvs_rs_str = ". " + _sa002_format_rs_diagnostic(
                        f"{niche_etf_ticker} vs {resolved_etf}",
                        metrics["Niche_vs_Sector_RS"],
                        metrics["Niche_vs_Sector_RS_Label"],
                        metrics["Niche_vs_Sector_RS_Spread_Mode"]
                    )

                niche_diag_block = f" [SUB-SECTOR] {niche_trend_str}{nvs_rs_str}."

        # ------------------------------------------------------------------
        # FINAL RETURN (both PASS and HALT paths)
        # ------------------------------------------------------------------
        final_status = "HALT" if is_halt else "PASS"
        full_diag = l1_diag + l2_commodity_diag + sector_context_diag + niche_diag_block
        return (final_status, full_diag, metrics)

    except Exception as e:
        import traceback
        return "ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", metrics
    finally:
        if _own_connection and ib.isConnected():
            ib.disconnect()


# ==============================================================================
# CLI OUTPUT FORMATTER
# Restructures the flat (status, diagnostic, metrics) tuple into grouped
# JSON for human readability. Internal metrics dict stays flat for
# orchestrator backward compatibility -- this is CLI-only.
# ==============================================================================

def _format_cli_output(status, diagnostic, metrics):
    """Convert flat audit results into grouped, readable JSON structure."""

    # Profile code -> bar timeframe for "close" disambiguation
    profile_str = metrics.get("Profile", "")
    if "(A)" in profile_str:
        bar_timeframe = "hourly"
    elif "(C)" in profile_str:
        bar_timeframe = "weekly"
    else:
        bar_timeframe = "daily"

    # --- Asset Identification ---
    asset = {
        "ticker":     metrics.get("Ticker"),
        "name":       metrics.get("Long_Name"),
        "profile":    metrics.get("Profile"),
        "ibkr_classification": {
            "industry":     metrics.get("IBKR_Industry"),
            "category":     metrics.get("IBKR_Category"),
            "subcategory":  metrics.get("IBKR_Subcategory"),
        },
    }

    # --- Sector ETF (single block: identification + floor check + context) ---
    sector_etf = metrics.get("Sector_ETF")
    gc = metrics.get("Sector_ETF_Golden_Cross")
    gc_label = "GOLDEN CROSS" if gc is True else ("DEATH CROSS" if gc is False else None)

    sector = {
        "ticker":       sector_etf,
        "name":         metrics.get("Sector_ETF_Name"),
        "detected_via": metrics.get("Sector_ETF_Source"),
        "bar_timeframe": bar_timeframe,
        "bar_close":    metrics.get("Sympathy_Close"),
        "floor":        metrics.get("Sympathy_Floor"),
        "floor_type":   metrics.get("Sympathy_Floor_Type"),
        "floor_check":  metrics.get("Sympathy_Status", status),
        "change_10bar": metrics.get("Sector_ETF_Change_10"),
        "change_20bar": metrics.get("Sector_ETF_Change_20"),
        "trend_20bar":  metrics.get("Sector_ETF_Trend"),
        "sma_cross":    gc_label,
    }

    # Add margin only on PASS
    if metrics.get("Sympathy_Margin") is not None:
        sector["margin"] = metrics["Sympathy_Margin"]
        sector["margin_pct"] = metrics.get("Sympathy_Margin_Pct")

    # Commodity Proxy (MOD-H, only when present)
    if metrics.get("Commodity_Proxy_ETF"):
        sector["commodity_proxy"] = {
            "ticker":     metrics["Commodity_Proxy_ETF"],
            "bar_close":  metrics.get("Commodity_Proxy_Close"),
            "floor":      metrics.get("Commodity_Proxy_Floor"),
            "floor_type": metrics.get("Commodity_Proxy_Floor_Type"),
            "floor_check": metrics.get("Commodity_Proxy_Status"),
            "margin_pct": metrics.get("Commodity_Proxy_Margin_Pct"),
        }

    # --- Relative Strength ---
    _PERF_LABELS = {
        "LEADING":     "outperforming",
        "INLINE":      "in line",
        "LAGGING":     "underperforming",
        "UNAVAILABLE": "UNAVAILABLE",
    }

    def _rs_entry(prefix, label_key, spread_key):
        val = metrics.get(prefix)
        lbl = metrics.get(label_key, "UNAVAILABLE")
        spread = metrics.get(spread_key, False)
        perf = _PERF_LABELS.get(lbl, lbl)
        if spread:
            return {"spread_pp": val, "performance": perf, "note": "percentage-point difference (ratio not meaningful)"}
        return {"ratio": val, "performance": perf}

    clean_ticker = metrics.get("Ticker", "ASSET")
    relative_strength = {
        f"{clean_ticker}_vs_{sector_etf}": _rs_entry("Asset_vs_Sector_RS", "Asset_vs_Sector_RS_Label", "Asset_vs_Sector_RS_Spread_Mode"),
        f"{sector_etf}_vs_SPY":            _rs_entry("Sector_vs_Market_RS", "Sector_vs_Market_RS_Label", "Sector_vs_Market_RS_Spread_Mode"),
        f"{clean_ticker}_vs_SPY":          _rs_entry("Asset_vs_Market_RS", "Asset_vs_Market_RS_Label", "Asset_vs_Market_RS_Spread_Mode"),
    }

    # --- Sub-Sector Niche ---
    niche_etf = metrics.get("Niche_ETF")
    sub_sector = None
    if niche_etf:
        sub_sector = {
            "ticker":       niche_etf,
            "name":         metrics.get("Niche_ETF_Name"),
            "change_20bar": metrics.get("Niche_ETF_Change_20"),
            "trend_20bar":  metrics.get("Niche_ETF_Trend"),
            f"{niche_etf}_vs_{sector_etf}": _rs_entry("Niche_vs_Sector_RS", "Niche_vs_Sector_RS_Label", "Niche_vs_Sector_RS_Spread_Mode"),
        }

    # --- Assemble ---
    output = {
        "status":             status,
        "asset":              asset,
        "sector_etf":         sector,
        "relative_strength":  relative_strength,
    }
    if sub_sector:
        output["sub_sector"] = sub_sector

    # --- Session RS (Profile A / SWING only) ---
    if "(A)" in profile_str and metrics.get("Session_Asset_Change") is not None:
        session_rs = {
            f"{clean_ticker}": f"{metrics['Session_Asset_Change']}%",
            f"{sector_etf}":   f"{metrics.get('Session_Sector_Change')}%",
            "SPY":             f"{metrics.get('Session_SPY_Change')}%",
            f"{clean_ticker}_vs_{sector_etf}": _rs_entry("Session_Asset_vs_Sector_RS", "Session_Asset_vs_Sector_RS_Label", "Session_Asset_vs_Sector_RS_Spread_Mode"),
            f"{sector_etf}_vs_SPY":            _rs_entry("Session_Sector_vs_Market_RS", "Session_Sector_vs_Market_RS_Label", "Session_Sector_vs_Market_RS_Spread_Mode"),
            f"{clean_ticker}_vs_SPY":          _rs_entry("Session_Asset_vs_Market_RS", "Session_Asset_vs_Market_RS_Label", "Session_Asset_vs_Market_RS_Spread_Mode"),
        }
        output["todays_session"] = session_rs

    return output


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBS Sympathy Audit (Step 4b) - Sector ETF floor check per Doc 5 Sec 3.1"
    )
    parser.add_argument("--ticker", required=True,
                        help="Asset ticker to audit (e.g. TNK, MSFT, KALU)")
    parser.add_argument("--profile", default="TREND",
                        help="Trade profile: SWING (A), TREND (B), WEALTH (C)")
    parser.add_argument("--sector-etf", default=None,
                        help="Manual sector ETF override (e.g. XLE, XLK). "
                             "If omitted, auto-detected via IBKR GICS metadata.")
    parser.add_argument("--mode", default="INFO",
                        help="INFO (paper/read-only port 4002) or LIVE (port 4001)")
    parser.add_argument("--raw", action="store_true",
                        help="Output raw flat metrics (orchestrator format) instead of grouped CLI format.")
    args = parser.parse_args()

    # Profile validation
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

    status, diag, metrics = run_sympathy_audit(
        args.ticker, args.profile, args.sector_etf, args.mode
    )

    if args.raw:
        # Raw flat output (same as orchestrator sees)
        print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))
    else:
        # Grouped CLI output
        output = _format_cli_output(status, diag, metrics)
        print(json.dumps(output, indent=4))

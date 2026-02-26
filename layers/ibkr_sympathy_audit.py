import json
import os
import argparse
from ib_insync import IB, Contract, util, Stock
import pandas as pd
import pandas_ta as ta
import asyncio

# TBS SYMPATHY AUDIT (Step 4b) v8.3
# Standalone pre-gate for the 8-Step Pipeline [DOC 5 SEC 3.1 / DOC 7 STEP 4]
# Verifies: Sector ETF closing ABOVE the Profile-dependent Structural Floor.
# Floor mapping: Profile A = VWAP, Profile B = Daily SMA 50, Profile C = Weekly SMA 200.
# GICS auto-detection via IBKR reqContractDetails metadata.
# CLI --sector-etf override always takes priority over auto-detection.

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
    "XLB", "XLC", "XLU", "XLRE", "XBI", "IBB",
}


# ==============================================================================
# SYMPATHY AUDIT FUNCTION
# ==============================================================================

def run_sympathy_audit(ticker, profile="TREND", sector_etf_override=None, mode="INFO"):
    """
    Standalone Sympathy Audit per Doc 5 Sec 3.1 / Doc 7 Step 4.

    Resolution priority:
      1. --sector-etf CLI override (operator always wins)
      2. IBKR industry-level auto-detection (most specific)
      3. IBKR category-level auto-detection (broad GICS)
      4. SKIP with diagnostic (unmapped -- operator must add mapping or use CLI)

    Returns: (status, diagnostic, metrics) tuple
      status:     "PASS" | "HALT" | "EXEMPT" | "SKIPPED" | "ERROR"
      diagnostic: Human-readable explanation
      metrics:    Dict with audit trail
    """

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 30 + (os.getpid() % 100)  # Offset from purity engine (25+)
    port = 4002 if mode.upper() == "INFO" else 4001

    ib = IB()
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
        ib.connect('127.0.0.1', port, clientId=unique_client_id)
        ib.reqMarketDataType(1)  #
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

        # --- VERDICT ---
        if sector_close < sector_floor_raw:
            metrics["Sympathy_Status"] = "FAIL"
            return (
                "HALT",
                f"SYMPATHY AUDIT FAILED: Sector ETF '{resolved_etf}' "
                f"close ({sector_close_display}) is BELOW its Structural Floor "
                f"({floor_label} = {sector_floor_display}). "
                f"Asset '{clean_ticker}' is BLOCKED per Doc 5 Sec 3.1.",
                metrics
            )
        else:
            margin = round(sector_close - sector_floor_raw, 2)
            margin_pct = round((sector_close - sector_floor_raw) / sector_floor_raw * 100, 2)
            metrics["Sympathy_Status"] = "PASS"
            metrics["Sympathy_Margin"] = margin
            metrics["Sympathy_Margin_Pct"] = margin_pct
            return (
                "PASS",
                f"SYMPATHY AUDIT PASSED: Sector ETF '{resolved_etf}' "
                f"close ({sector_close_display}) is ABOVE its Structural Floor "
                f"({floor_label} = {sector_floor_display}). "
                f"Margin: +{margin} ({margin_pct}%).",
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
    print(json.dumps({"status": status, "diagnostic": diag, "metrics": metrics}, indent=4))

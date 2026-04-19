import os
import math
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pandas_ta as ta  # Side-effect: registers .ta accessor
from ib_insync import IB, util, Stock
from tbs_engine.types import ProfileConfig, StateBundle

__all__ = ['_build_config', '_classify_state', '_fetch_and_compute', 'CRYPTO_TICKERS',
           'EXCHANGE_TZ', 'EXCHANGE_LABEL', 'SESSION_CLOSE']

# Crypto tickers — not supported by the equity pipeline.
# Engine uses Stock() constructor which resolves these to ETF proxies
# (e.g., BTC → Grayscale Bitcoin Mini ETF), not the actual cryptocurrency.
# See CRYPTO-001 for future native crypto support.
CRYPTO_TICKERS = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "MATIC"}

# PE-42: Exchange timezone mapping — static constant for data_basis transparency
EXCHANGE_TZ = {
    "NASDAQ":   "America/New_York",
    "NYSE":     "America/New_York",
    "ARCA":     "America/New_York",
    "AMEX":     "America/New_York",
    "NYSENBBO": "America/New_York",
    "LSE":      "Europe/London",
    "LSEETF":   "Europe/London",
}
EXCHANGE_LABEL = {
    "America/New_York": "ET",
    "Europe/London":    "London",
}
# PE-43: Session close times (hour, minute) by timezone — for bar_range_str cosmetic fix
SESSION_CLOSE = {
    "America/New_York": (16, 0),    # US equities: 16:00 ET
    "Europe/London":    (16, 30),   # LSE equities: 16:30 London
}
# Fallback for unknown exchanges: use "UTC" label

# ======================================================================


def _build_config(p_code):
    """Factory: build the correct ProfileConfig for a given p_code.

    RFT-001 Phase 4 | Spec §III.2
    """
    if p_code == "A":
        return ProfileConfig(
            iq=-1,                      # PE-43: was -2 (incorrect assumption about in-progress hourly bars)
            min_bars_required=30,
            window_limit=4,
            ff_threshold=8,
            ext_limit_trending=99.0,    # AVWAP-001 DQ-4: Sentinel — intraday extension gate RETIRED for Profile A
            ext_limit_resolving=99.0,   # AVWAP-001 DQ-4: Sentinel — PA-001 daily gate is sole overextension check
            ext_limit_etf=99.0,         # AVWAP-001 DQ-4: Sentinel — ETF also uses daily gate only
            resistance_slice_start=-11,  # PE-43: was -12 (10-bar window ending at iq=-1)
            resistance_slice_end=-1,     # PE-43: was -2 (aligned with iq=-1)
            tf_resolution="1 hour",
            tf_duration="3 M",
            ctx_resolution="1 day",
            ctx_duration="12 M",
            fb_max=2.0,
            ta_max=30,
            prev_bar_offset=2,           # PE-43: was 3 (one bar before iq, same as B/C)
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50"),
            pb_upper_col="EMA_21",      # AVWAP-001 DQ-2: transitional — trigger.py overrides with daily zone
        )
    elif p_code == "B":
        return ProfileConfig(
            iq=-1,
            min_bars_required=220,
            window_limit=5,
            ff_threshold=4,
            ext_limit_trending=1.0,
            ext_limit_resolving=0.5,
            ext_limit_etf=0.5,
            resistance_slice_start=-11,
            resistance_slice_end=-1,
            tf_resolution="1 day",
            tf_duration="2 Y",
            ctx_resolution="1 week",
            ctx_duration="5 Y",
            fb_max=3.0,
            ta_max=80,
            prev_bar_offset=2,
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50", "SMA_200"),
            pb_upper_col="EMA_21",
        )
    elif p_code == "C":
        return ProfileConfig(
            iq=-1,
            min_bars_required=220,
            window_limit=4,
            ff_threshold=4,
            ext_limit_trending=1.0,    # PE-CAL-1 §6.4: SMA 200 anchor, 1.0 ATR
            ext_limit_resolving=1.0,   # Same as trending for Profile C
            ext_limit_etf=0.5,
            resistance_slice_start=-11,
            resistance_slice_end=-1,
            tf_resolution="1 week",
            tf_duration="10 Y",
            ctx_resolution="1 month",
            ctx_duration="20 Y",
            fb_max=5.0,
            ta_max=60,
            prev_bar_offset=2,
            required_ma_cols=("EMA_8", "EMA_21", "SMA_50", "SMA_200"),
            pb_upper_col="ANCHOR",
        )
    else:
        raise ValueError(f"Unknown p_code: {p_code}")




# ======================================================================
# RFT-001 PHASE 5: StateBundle Dataclass + State Classification Extraction
# Spec §III.4 (Layer 2 — State Classification)
# ======================================================================



def _classify_state(df, p_code, is_etf, cfg, raw_metrics):
    """Layer 2: State Classification.

    Absorbs the ~120-line ENGINE STATE CLASSIFICATION block from
    run_tbs_engine(). Receives the DataFrame, profile code, ETF flag,
    ProfileConfig, and raw_metrics dict. Returns a StateBundle.

    Signature adapted from spec (df, p_code, is_etf, cfg) to also
    accept raw_metrics for scalar extraction per §4.4 design intent.
    """
    # --- Scalar extraction from raw_metrics ---
    adx_t    = raw_metrics["adx_t"]
    adx_t1   = raw_metrics["adx_t1"]
    adx_t2   = raw_metrics["adx_t2"]
    di_plus  = raw_metrics["di_plus"]
    di_minus = raw_metrics["di_minus"]
    ma_squeeze = raw_metrics["ma_squeeze"]
    atr_raw  = raw_metrics["atr_raw"]

    last = df.iloc[cfg.iq]

    # RESOLVING: ADX > 20, 3-bar positive slope, no squeeze
    is_resolving = (
            (adx_t > 20) and
            (adx_t > adx_t1 > adx_t2) and
            not ma_squeeze
    )

    # TRENDING: ADX > 25 AND full 4-level MA stack (Price > EMA8 > EMA21 > SMA50)
    # State Persistence Rule  [MANDATE: DOC 2 SEC 4.2]
    # Initial confirmation requires ADX > 25 + full MA stack.
    # Persistence during pullback: ADX may soften to 20-25 by mathematical
    # construction (Wilder) while the MA stack remains intact. As long as
    # ADX > 20 (directional regime confirmed) AND MA stack is fully stacked,
    # TRENDING state is preserved. If MA stack breaks, state revokes immediately
    # regardless of ADX level.
    ma_stack_full = (
            last['close']  > last['EMA_8']  and
            last['EMA_8']  > last['EMA_21'] and
            last['EMA_21'] > last['SMA_50'] and
            # [CRG-1] Golden Cross: Profile B TRENDING requires SMA 50 > SMA 200.
            # Profile A: handled by Context Regime Gate. Profile C: exempt (counter-cyclical).
            # NaN guard: NaN SMA_200 evaluates False, blocking TRENDING (Ambiguity Clause §XI).
            (p_code != "B" or (not pd.isna(last['SMA_200']) and last['SMA_50'] > last['SMA_200']))
    )
    is_trending = ma_stack_full and (adx_t > 20) and not ma_squeeze

    # EMA stacked: EMA8 > EMA21 -- used solely for Profile A DI exemption
    ema_stacked = last['EMA_8'] > last['EMA_21']

    # ETF Logic Lock  [Doc 6 §3.4.1 / Doc 2 §4.2.1]
    # Suppresses EMA 8 floor re-assignment by zeroing is_trending / is_resolving.
    # These zeroed flags correctly prevent Convexity Protocol activation (ANCHOR
    # stays baseline MA, no EMA 8 exit signal, no EMA 8 proximity anchor).
    # Entry eligibility is preserved separately via _etf_entry_* snapshots
    # so Phase 4 can still route ETFs through Pullback / Breakout / Reclaim
    # protocols using their baseline floors.  [PE-BUG-1 FIX]
    if is_etf:
        _etf_entry_trending  = is_trending    # snapshot before Lock
        _etf_entry_resolving = is_resolving   # snapshot before Lock
        is_resolving = False                  # Lock: floor policy only
        is_trending  = False                  # Lock: floor policy only
    else:
        _etf_entry_trending  = False
        _etf_entry_resolving = False

    # [BUG #40 FIX -- REFINED] Demote RESOLVING when ADX slope is positive but
    # the structural direction is bearish. ADX measures trend STRENGTH, not
    # direction -- a rising ADX with -DI > +DI means the DOWNTREND is
    # strengthening, not that a bullish regime is forming.
    #
    # Original fix used a 15-point DI-spread threshold which proved too wide:
    #   ISRG TREND:  spread 14.88 -- missed (EMA inverted, price $40 below SMA_50)
    #   ISRG WEALTH: spread 10.46 -- missed (EMA inverted, clearly bearish weekly)
    #
    # Revised criteria -- ALL must be true:
    #   1. is_resolving is True (ADX > 20, 3-bar positive slope)
    #   2. EMA stack is inverted (EMA_8 < EMA_21) -- short-term structure broken.
    #      This is the primary structural signal. A bullish RESOLVING setup
    #      requires the fast EMA above the slow EMA to support the breakout thesis.
    #   3. -DI > +DI -- directional flow confirms downside, not upside.
    #      Combined with EMA inversion this is unambiguous bearish context.
    #   4. MA stack is not full -- no structural bull confirmation exists.
    #
    # The DI spread magnitude is dropped as a criterion. Any -DI dominance on
    # an inverted EMA stack is sufficient -- the threshold was arbitrary and
    # generated false negatives on legitimate demotion candidates.
    _resolving_is_bearish = (
            is_resolving and
            not ema_stacked and       # EMA_8 < EMA_21: short-term structure broken
            (di_minus > di_plus) and  # -DI dominant: directional flow is bearish
            not ma_stack_full         # no bullish MA confirmation
    )
    # [PE-CAL-1 FIX §6.6] Profile C counter-cyclical exemption. WEALTH entries
    # at the SMA 200 are inherently counter-cyclical: the asset has declined to its
    # long-term floor, so -DI dominance and EMA inversion are expected by construction.
    # Demotion is suppressed when price is within 5% of SMA 200 AND ADX slope is
    # positive (directional energy building, even if currently bearish).
    _c_near_floor = False
    if p_code == "C" and 'SMA_200' in df.columns and not pd.isna(last['SMA_200']) and last['SMA_200'] > 0:
        _c_floor_dist_pct = abs(last['close'] - last['SMA_200']) / last['SMA_200'] * 100
        _c_near_floor = _c_floor_dist_pct <= 5.0 and (adx_t > adx_t1)  # within 5% + positive ADX slope
    if _resolving_is_bearish and not _c_near_floor:
        is_resolving = False

    # [PE-BUG-1 FIX] Apply identical bearish demotion to ETF entry snapshot.
    # Without this, an ETF with inverted EMAs and -DI dominance would still
    # reach Phase 4 RESOLVING branch via the _etf_entry_resolving flag.
    if _etf_entry_resolving and not ema_stacked and (di_minus > di_plus) and not ma_stack_full:
        _etf_entry_resolving = False

    # Composite entry-eligibility flags  [PE-BUG-1 FIX]
    # Used at Phase 4 decision chain + Gate 6 DI exemption.
    # For non-ETF: _etf_entry_* are False, so these equal is_trending/is_resolving.
    # For ETF: is_trending/is_resolving are False (Lock), so these equal _etf_entry_*.
    _entry_trending  = is_trending  or _etf_entry_trending
    _entry_resolving = is_resolving or _etf_entry_resolving

    return StateBundle(
        is_trending=is_trending,
        is_resolving=is_resolving,
        ma_stack_full=ma_stack_full,
        ma_squeeze=ma_squeeze,
        ema_stacked=ema_stacked,
        adx_t=adx_t,
        adx_t1=adx_t1,
        di_plus=di_plus,
        di_minus=di_minus,
        atr_raw=atr_raw,
        _etf_entry_trending=_etf_entry_trending,
        _etf_entry_resolving=_etf_entry_resolving,
        _entry_trending=_entry_trending,
        _entry_resolving=_entry_resolving,
        _resolving_is_bearish=_resolving_is_bearish,
    )






def _fetch_iv_streaming(ib, contract, initial_sleep=2, max_polls=4, poll_interval=1):
    """Fetch implied volatility via streaming reqMktData with poll-loop.

    IBKR rejects snapshot=True + genericTickList (Error 321).
    This uses streaming mode (snapshot=False) with a hybrid poll budget:
    - Initial sleep of `initial_sleep` seconds (covers RTH happy path)
    - Up to `max_polls` additional 1s polls if IV not yet populated (covers after-hours)
    - Total max wall-time: initial_sleep + (max_polls * poll_interval) = 6s default

    Returns float IV or None on timeout/error.
    Reference: IVR-001-BUG-4-SUB-1.
    """
    _iv_raw = None
    try:
        _iv_ticker = ib.reqMktData(contract, '106', False, False)
        ib.sleep(initial_sleep)
        _iv_candidate = getattr(_iv_ticker, 'impliedVolatility', None)
        if _iv_candidate is not None and not (
            isinstance(_iv_candidate, float) and math.isnan(_iv_candidate)
        ):
            _iv_raw = _iv_candidate
        else:
            for _ in range(max_polls):
                ib.sleep(poll_interval)
                _iv_candidate = getattr(_iv_ticker, 'impliedVolatility', None)
                if _iv_candidate is not None and not (
                    isinstance(_iv_candidate, float) and math.isnan(_iv_candidate)
                ):
                    _iv_raw = _iv_candidate
                    break
        ib.cancelMktData(contract)
    except Exception:
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass
    return _iv_raw


def _fetch_and_compute(ticker, p_code, cfg, profile, is_etf_arg, mode, exchange, currency, convexity_class):
    """Layer 1: Data Fetch and Indicator Computation.

    Creates IB connection, fetches historical data, computes indicator stack,
    extracts scalar values, performs SSG-001 stop adjustment, and fetches
    context data. IB connection is created and closed within this function.

    Returns tuple[DataFrame, dict]:
        - DataFrame with full indicator stack
        - raw_metrics dict containing scalar values, metadata, and df_ctx.
          On early exit (error/halt): raw_metrics["_early_return"] = (status, diag, metrics)
          and DataFrame is None.

    RFT-001 Phase 4 | Spec §III.3
    """

    raw = {}  # raw_metrics accumulator

    # --- [MANDATE: CONCURRENCY INTEGRITY] ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    unique_client_id = 25 + (os.getpid() % 100)
    port = 4002 if mode.upper() == "INFO" else 4001

    ib = IB()

    # Suppress Error 162 (NYSENBBO routing)
    class _SuppressError162(logging.Filter):
        def filter(self, record):
            return 'Error 162' not in record.getMessage()
    logging.getLogger('ib_insync.wrapper').addFilter(_SuppressError162())

    metrics = {}  # [MANDATE: DOC 8 SEC 39] SSoT Handshake initialisation

    # EPX-001: PROXIMITY SIGNAL FIELD INITIALIZATION
    metrics["Proximity_Signal"]        = None
    metrics["Proximity_Blocking_Gate"] = None
    metrics["Proximity_Distance"]      = None
    metrics["Proximity_Target"]        = None
    metrics["Proximity_Note"]          = None

    # --- [MANDATE: DOC 8 SEC 23] DYNAMIC ROUTING ---
    clean_ticker = ticker.upper()
    p_exchange   = ""
    routing_map  = {
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

    if clean_ticker == "VWRP" and currency == "USD":
        exchange, currency, p_exchange = "SMART", "GBP", "LSE"

    # --- PE-40: CRYPTO ASSET INTERIM MITIGATION GUARD ---
    # Must fire before any IBKR connection (ib.connect / Stock / reqContractDetails / reqHistoricalData).
    # See CRYPTO-001 for future native crypto support.
    if clean_ticker in CRYPTO_TICKERS:
        raw["_early_return"] = (
            "HALT",
            f"REJECT (reason: UNSUPPORTED ASSET CLASS). {clean_ticker} is a cryptocurrency — "
            f"the engine's Stock() constructor resolves this to an ETF proxy (e.g., Grayscale), "
            f"not the actual cryptocurrency. Run is aborted to prevent analysing the wrong instrument. "
            f"See CRYPTO-001 for future native crypto support.",
            metrics
        )
        return None, raw

    try:
        ib.connect('127.0.0.1', port, clientId=unique_client_id)
        ib.reqMarketDataType(1)

        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)

        # --- [MANDATE: DOC 8 SEC 467] INDEPENDENT ASSET IDENTIFICATION ---
        _is_lse_etf = False
        is_etf = is_etf_arg  # start with caller's value; may be overridden by metadata
        _etf_detection_source = "CLI_FLAG" if is_etf_arg else "NONE"
        _etf_primary_exchange = ""
        details = ib.reqContractDetails(contract)
        if details:
            meta = details[0].longName.upper()
            etf_keywords = [
                ' ETF', 'ETF ', 'FUND', 'VANGUARD', 'VANG', 'ISHARES', 'UCITS',  # [PE-34] Space-delimited ETF: prevents NETFLIX substring match
                'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES'
            ]
            if any(key in meta for key in etf_keywords):
                is_etf = True
                if _etf_detection_source == "NONE":
                    _etf_detection_source = "KEYWORD"

            qualified = details[0].contract
            primary_exch = getattr(qualified, 'primaryExchange', '') or getattr(details[0], 'primaryExch', '')
            _etf_primary_exchange = primary_exch
            if 'ETF' in primary_exch.upper() and currency == "GBP":  # [PE-33] Guard: exchange-code ETF detection is LSE-only
                is_etf = True
                _is_lse_etf = True
                if _etf_detection_source != "CLI_FLAG":
                    _etf_detection_source = "EXCHANGE_CODE"
            if primary_exch == 'NYSENBBO':
                qualified.primaryExchange = 'NYSE'
            contract = qualified

        # [PE-33] ETF diagnostic fields — always populated for forensic visibility
        metrics["Is_ETF"] = is_etf
        metrics["ETF_Detection_Source"] = _etf_detection_source
        metrics["ETF_Primary_Exchange"] = _etf_primary_exchange

        res = cfg.tf_resolution
        dur = cfg.tf_duration

        bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True, formatDate=2)

        # --- NYSENBBO RETRY GUARD ---
        nyse_retry_used = False
        if not bars and currency == "USD":
            contract.exchange        = 'NYSE'
            contract.primaryExchange = 'NYSE'
            bars = ib.reqHistoricalData(contract, '', dur, res, 'TRADES', True, formatDate=2)
            nyse_retry_used = bool(bars)

        if not bars:
            raw["_early_return"] = ("ERROR", f"No data retrieved for {clean_ticker}", {})
            return None, raw

        df = util.df(bars)
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        # --- NYSE RETRY VOLUME PATCH ---
        if nyse_retry_used:
            smart_contract = Stock(clean_ticker, 'SMART', currency)
            vol_dur = '3 M' if 'day' in res else ('6 M' if 'week' in res else '2 Y')
            try:
                vol_bars = ib.reqHistoricalData(smart_contract, '', vol_dur, res, 'TRADES', True)
                if vol_bars:
                    df_vol = util.df(vol_bars)
                    df_vol.set_index('date', inplace=True)
                    df_vol.index = pd.to_datetime(df_vol.index)
                    df_vol.sort_index(inplace=True)
                    common_idx = df.index.intersection(df_vol.index)
                    if len(common_idx) > 10:
                        df.loc[common_idx, 'volume'] = df_vol.loc[common_idx, 'volume']
            except Exception:
                pass

        # --- DATA SUFFICIENCY GUARD ---
        if len(df) < cfg.min_bars_required:
            raw["_early_return"] = (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). Insufficient historical data: {len(df)} bars retrieved "
                f"(requires >= {cfg.min_bars_required} for Profile {p_code}). "
                f"Ticker may be too new or have limited exchange history for SMA_200 calculation.",
                metrics
            )
            return None, raw

        # --- TIMEFRAME NORMALIZATION ---
        bars_per_day = (
            8.0 if currency == "GBP" else
            8.5 if currency == "EUR" else
            6.5
        ) if "hour" in res else (
            1.0 / 5.0  if "week"  in res else
            1.0 / 21.0 if "month" in res else
            1.0
        )
        sma_20_length = int(20 * bars_per_day) if "hour" in res else (
            20  if "day"   in res else
            20  if "week"  in res else
            12  if "month" in res else
            20
        )

        # --- INDICATOR STACK ---
        df.ta.ema(length=8,  append=True)
        df.ta.ema(length=21, append=True)
        df.ta.sma(length=50,  append=True)
        df.ta.sma(length=200, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.sma(close=df['volume'], length=9,             append=True, col_names=('vol_sma_9',))
        df.ta.sma(close=df['volume'], length=sma_20_length, append=True, col_names=('vol_sma_20',))

        # --- MA COLUMN EXISTENCE GUARD ---
        for col in cfg.required_ma_cols:
            if col not in df.columns or df[col].isna().all():
                raw["_early_return"] = (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {col} is entirely NaN. "
                    f"Insufficient price history for this indicator on {clean_ticker}.",
                    metrics
                )
                return None, raw

        # [PE-18 / PE-24 FIX] Existence guard for ATR and Volume SMA columns.
        for ind_col in ['ATRr_14', 'vol_sma_9', 'vol_sma_20']:
            if ind_col not in df.columns or df[ind_col].isna().all():
                raw["_early_return"] = (
                    "HALT",
                    f"REJECT (reason: DATA INTEGRITY). Indicator computation failed: {ind_col} is entirely NaN or missing. "
                    f"pandas_ta may have failed for {clean_ticker}.",
                    metrics
                )
                return None, raw

        # --- COLUMN IDENTIFICATION ---
        adx_candidates = [c for c in df.columns if c.startswith('ADX') and 'DM' not in c]
        dmp_candidates = [c for c in df.columns if 'DMP' in c]
        dmn_candidates = [c for c in df.columns if 'DMN' in c]

        if not adx_candidates:
            raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). ADX column not found -- pandas_ta.adx() failed or insufficient data.", metrics)
            return None, raw
        if not dmp_candidates or not dmn_candidates:
            raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). Directional Movement columns (DI+/DI-) not found.", metrics)
            return None, raw

        adx_col = adx_candidates[0]
        dmp_col = dmp_candidates[0]
        dmn_col = dmn_candidates[0]

        # Scalar extraction using cfg.iq
        _iq = cfg.iq

        adx_t   = df[adx_col].iloc[_iq]
        adx_t1  = df[adx_col].iloc[_iq - 1]
        adx_t2  = df[adx_col].iloc[_iq - 2]
        di_plus  = df[dmp_col].iloc[_iq]
        di_minus = df[dmn_col].iloc[_iq]

        # [PE-19 FIX] NaN guard on ADX/DI values
        if any(pd.isna(v) for v in [adx_t, adx_t1, adx_t2, di_plus, di_minus]):
            raw["_early_return"] = (
                "HALT",
                f"REJECT (reason: DATA INTEGRITY). ADX/DI indicator values contain NaN at evaluated bar. "
                f"Insufficient data for trend classification on {clean_ticker}.",
                metrics
            )
            return None, raw

        # ADX SLOPE ACCELERATION
        adx_slope_t  = adx_t  - adx_t1
        adx_slope_t1 = adx_t1 - adx_t2
        adx_accel    = round(adx_slope_t - adx_slope_t1, 2)
        adx_accel_state = (
            "ACCELERATING" if adx_accel > 0.3 else
            "DECELERATING" if adx_accel < -0.3 else
            "CRUISING"
        )

        # --- MA SQUEEZE ---
        df['MA_Dist'] = abs(df['EMA_8'] - df['EMA_21'])
        df['Squeeze'] = df['MA_Dist'] < (0.1 * df['ATRr_14'])
        ma_squeeze    = bool(
            df['Squeeze'].iloc[_iq] and df['Squeeze'].iloc[_iq - 1] and df['Squeeze'].iloc[_iq - 2]
        )

        # Use last completed bar for Profile A (1H) to enforce BAR CLOSE cadence.
        last = df.iloc[cfg.iq]

        # --- PRE-COMPUTE RESISTANCE ---
        resistance_raw = float(df['high'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].max())

        # --- BASELINE ANCHOR COMPUTATION ---
        # Profile A: AVWAP-001 DQ-1 — Hourly EMA 21 replaces VWAP as structural floor.
        #   Session VWAP retained in df['SESSION_VWAP'] for trigger layer (DQ-9) and
        #   informational output (DQ-6).
        # Profile B: SMA_50 baseline (Convexity override to EMA_8 happens in run_tbs_engine after state classification)
        # Profile C: SMA_200 (state-independent)
        # ETF: baseline MA for the profile
        vwap_col = None
        if p_code == "A":
            df.ta.vwap(append=True)
            vwap_cols = [c for c in df.columns if 'VWAP' in c]
            if not vwap_cols:
                raw["_early_return"] = ("HALT", "REJECT (reason: DATA INTEGRITY). VWAP column not found -- pandas_ta.vwap() failed or insufficient data.", metrics)
                return None, raw
            vwap_col = vwap_cols[0]
            df['SESSION_VWAP'] = df[vwap_col]   # AVWAP-001: retain for trigger layer (DQ-9) and informational output (DQ-6)
            df['ANCHOR'] = df['EMA_21']          # AVWAP-001 DQ-1: hourly EMA 21 replaces VWAP as structural floor
        elif p_code == "B":
            # Baseline: SMA_50 for both ETF and equity. Convexity override (EMA_8)
            # applied in run_tbs_engine after state classification (equity only; ETF
            # Logic Lock prevents override).
            df['ANCHOR'] = df['SMA_50']
        elif p_code == "C":
            df['ANCHOR'] = df['SMA_200']

        # Re-read last row after ANCHOR column is computed
        last = df.iloc[cfg.iq]

        # --- SCALING & HARD STOP ---
        price_scaler         = 1.0 if (_is_lse_etf and currency == "GBP") else (100.0 if currency == "GBP" else 1.0)  # [PE-33] Belt-and-suspenders
        actual_price         = last['close'] / price_scaler
        atr_raw              = float(last['ATRr_14'])
        structural_floor_raw = last['ANCHOR']
        hard_stop_raw = structural_floor_raw - (1.5 * atr_raw)

        # --- SSG-001 + SSG-002: STRUCTURAL STOP AUDIT with PROXIMITY QUALIFIER ---
        # SSG-001: Detects hard stop above Established Hourly Low.
        # SSG-002: Adds proximity gate — remedy fires only when gap < 0.5 ATR.
        #          Wide-gap cases leave stop unchanged (proximity_blocked).
        SSG_PROXIMITY_THRESHOLD = 0.5   # ATR units (SSG-002)
        _ssg_adjusted = False
        _ssg_original_raw = None
        _ssg_reason = None
        _ssg_proximity_blocked = False
        _ssg_gap_atr = None
        _ssg_hourly_low = float(df['low'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].min())
        if hard_stop_raw > _ssg_hourly_low:
            _gap = hard_stop_raw - _ssg_hourly_low
            _gap_atr = _gap / atr_raw if atr_raw > 0 else float('inf')
            _ssg_gap_atr = round(_gap_atr, 2)
            _ssg_original_raw = hard_stop_raw
            if _gap_atr < SSG_PROXIMITY_THRESHOLD:
                # Near-miss: apply SSG-001 remedy
                hard_stop_raw = _ssg_hourly_low - (0.25 * atr_raw)
                _ssg_adjusted = True
                _ssg_proximity_blocked = False
                _ssg_reason = (
                    f"Hard stop ({round(_ssg_original_raw / price_scaler, 2)}) above "
                    f"Established Hourly Low ({round(_ssg_hourly_low / price_scaler, 2)}) "
                    f"by {_ssg_gap_atr} ATR -- within proximity threshold ({SSG_PROXIMITY_THRESHOLD} ATR), "
                    f"stop adjusted to {round(hard_stop_raw / price_scaler, 2)} "
                    f"(Hourly Low - 0.25 ATR)."
                )
            else:
                # Wide-gap: no adjustment (SSG-002 proximity block)
                _ssg_adjusted = False
                _ssg_proximity_blocked = True
                _ssg_reason = (
                    f"Hard stop ({round(_ssg_original_raw / price_scaler, 2)}) above "
                    f"Established Hourly Low ({round(_ssg_hourly_low / price_scaler, 2)}) "
                    f"by {_ssg_gap_atr} ATR -- outside proximity threshold ({SSG_PROXIMITY_THRESHOLD} ATR), "
                    f"no adjustment applied."
                )
        metrics["Stop_Proximity_Blocked"] = _ssg_proximity_blocked
        metrics["Stop_Gap_ATR"] = _ssg_gap_atr

        # --- CONTEXT DATA FETCH ---
        ctx_bars = ib.reqHistoricalData(contract, '', cfg.ctx_duration, cfg.ctx_resolution, 'TRADES', True, formatDate=2)
        df_ctx = None
        if ctx_bars:
            df_ctx = util.df(ctx_bars)
            df_ctx.set_index('date', inplace=True)
            df_ctx.index = pd.to_datetime(df_ctx.index)
            df_ctx.sort_index(inplace=True)
            for ln in [8, 21]:   df_ctx.ta.ema(length=ln, append=True)
            for ln in [50, 200]: df_ctx.ta.sma(length=ln, append=True)
            df_ctx.ta.sma(close=df_ctx['volume'], length=9, append=True, col_names=('vol_sma_9',))
            # PA-001: Daily ATR(14) for protective computations
            df_ctx.ta.atr(length=14, append=True)  # Creates ATRr_14 column on df_ctx
            # PA-001 DQ-8: Daily RSI(14) for advisory output
            df_ctx.ta.rsi(length=14, append=True)  # Creates RSI_14 column on df_ctx

        # PA-001 Step 2b: Extract daily protective values (Profile A only)
        daily_ema21 = 0.0
        daily_atr_val = 0.0
        daily_hard_stop = 0.0
        daily_rsi = None  # PA-001 DQ-8: Daily RSI(14)
        if p_code == "A" and df_ctx is not None and 'EMA_21' in df_ctx.columns and 'ATRr_14' in df_ctx.columns:
            _d_ema21 = df_ctx['EMA_21'].iloc[-1]
            _d_atr = df_ctx['ATRr_14'].iloc[-1]
            if not pd.isna(_d_ema21) and not pd.isna(_d_atr):
                daily_ema21 = float(_d_ema21)
                daily_atr_val = float(_d_atr)
                daily_hard_stop = daily_ema21 - (1.5 * daily_atr_val)
            # PA-001 DQ-8: Extract Daily RSI(14)
            if 'RSI_14' in df_ctx.columns:
                _d_rsi = df_ctx['RSI_14'].iloc[-1]
                daily_rsi = float(_d_rsi) if not pd.isna(_d_rsi) else None

        # ==================================================================
        # PE-42: LIVE PRICE SUPPLEMENT — Profile A only
        # reqMktData snapshot + post-close daily bar fallback + timezone mapping
        # Spec §IV.1: Changes 2–4
        # ==================================================================

        # --- PE-42 Change 1: Resolve exchange timezone ---
        # Use the resolved exchange from contract details (primary exchange
        # if available, else the routing exchange).
        _pe42_exchange = (
            getattr(contract, 'primaryExchange', '') or exchange
        ).upper()
        tz_name = EXCHANGE_TZ.get(_pe42_exchange, None)
        if tz_name:
            tz_label = EXCHANGE_LABEL.get(tz_name, tz_name)
        else:
            # Fallback: derive UTC offset from last bar timestamp
            _last_bar_ts = df.index[-1]
            if hasattr(_last_bar_ts, 'tzinfo') and _last_bar_ts.tzinfo is not None:
                _utc_offset = _last_bar_ts.strftime('%z')
                tz_label = f"UTC{_utc_offset[:3]}:{_utc_offset[3:]}" if _utc_offset else "UTC"
            else:
                tz_label = "UTC"
            tz_name = "UTC"

        # --- PE-42 Change 2: Bar range string (Profile A only) ---
        # IBKR hourly bar timestamps represent the BAR START time, not end.
        # A timestamp of 15:00 means the bar covers 15:00 to the next bar's start
        # (or session close for the final bar).
        #
        # Two edge cases where bars are NOT 1 hour:
        #   US first bar:  09:30-10:00 ET (30 min, market opens mid-hour)
        #   LSE last bar:  16:00-16:30 London (30 min, market closes mid-hour)
        #
        # Logic: use next bar's start if available (handles first-bar case),
        # otherwise use session close time (handles last-bar case).
        bar_range_str = None
        if p_code == "A":
            _eval_bar = df.iloc[cfg.iq]
            _bar_start_ts = df.index[cfg.iq]
            if hasattr(_bar_start_ts, 'tzinfo') and _bar_start_ts.tzinfo is not None:
                _bar_start_local = _bar_start_ts.astimezone(ZoneInfo(tz_name))
            else:
                _bar_start_local = _bar_start_ts

            # Determine bar end
            _next_iq = cfg.iq + 1
            if _next_iq < 0:
                # Next bar exists in DataFrame — use its start as this bar's end
                _next_ts = df.index[_next_iq]
                if hasattr(_next_ts, 'tzinfo') and _next_ts.tzinfo is not None:
                    _next_local = _next_ts.astimezone(ZoneInfo(tz_name))
                else:
                    _next_local = _next_ts
                # Sanity: must be same trading day (gap < 2 hours)
                _gap = _next_local - _bar_start_local
                if timedelta(0) < _gap <= timedelta(hours=2):
                    _bar_end_local = _next_local
                else:
                    # Next bar is next trading day — use session close
                    _close_h, _close_m = SESSION_CLOSE.get(tz_name, (16, 0))
                    _bar_end_local = _bar_start_local.replace(
                        hour=_close_h, minute=_close_m, second=0, microsecond=0)
            else:
                # Evaluated bar is the last in DataFrame — use session close
                _close_h, _close_m = SESSION_CLOSE.get(tz_name, (16, 0))
                _bar_end_local = _bar_start_local.replace(
                    hour=_close_h, minute=_close_m, second=0, microsecond=0)
                # Defensive: if bar_start >= session close (shouldn't happen with RTH),
                # fall back to +1 hour
                if _bar_end_local <= _bar_start_local:
                    _bar_end_local = _bar_start_local + timedelta(hours=1)

            bar_range_str = f"{_bar_start_local.strftime('%H:%M')}-{_bar_end_local.strftime('%H:%M')}"

        # --- PE-42 Change 3: reqMktData snapshot (Profile A only) ---
        live_price = float('nan')
        snapshot_time_str = None
        price_source = "BAR"  # default for Profile B/C
        _iv_raw_from_mktdata = None  # IVR-001: IV populated by reqMktData

        if p_code == "A":
            try:
                # IVR-001-BUG-4: Primary call carries price/volume only (no tick
                # 106). Tick 106 moved to separate snapshot call below — streaming
                # mode was unreliable for the computed IV tick after hours.
                ticker_obj = ib.reqMktData(contract, '', False, False)
                ib.sleep(2)  # allow snapshot to populate
                _raw_live = ticker_obj.marketPrice()
                # VOL-004: cumulative session volume from ticker snapshot
                _raw_session_vol = getattr(ticker_obj, 'volume', float('nan'))
                # PE-42 BUG FIX: marketPrice() returns native units (e.g. pence for GBP).
                # Must scale to display currency to match bar_close_price units.
                live_price = _raw_live / price_scaler if not math.isnan(_raw_live) else _raw_live
                snapshot_time = datetime.now(ZoneInfo(tz_name))
                snapshot_time_str = snapshot_time.strftime("%H:%M:%S")
                ib.cancelMktData(contract)
            except Exception:
                live_price = float('nan')
                _raw_session_vol = float('nan')  # VOL-004: session vol unavailable on exception
                snapshot_time = datetime.now(ZoneInfo(tz_name))
                snapshot_time_str = snapshot_time.strftime("%H:%M:%S")
                try:
                    ib.cancelMktData(contract)
                except Exception:
                    pass

            # IVR-001-BUG-4-SUB-1: streaming mode + poll-loop (replaces invalid snapshot+generic-tick pattern)
            _iv_raw_from_mktdata = _fetch_iv_streaming(ib, contract)

            # VOL-004: Convert raw session volume to clean int or None
            _session_vol = None
            if _raw_session_vol is not None and not (isinstance(_raw_session_vol, float) and math.isnan(_raw_session_vol)):
                _session_vol = int(_raw_session_vol)  # volume is always whole shares

            # --- PE-42 Change 4: Post-close daily bar fallback ---
            if math.isnan(live_price) and df_ctx is not None and len(df_ctx) > 0:
                live_price = float(df_ctx.iloc[-1]['close']) / price_scaler
                price_source = "DAILY_CLOSE"
            else:
                price_source = "LIVE" if not math.isnan(live_price) else "UNAVAILABLE"
        else:
            # Profile B/C: snapshot_time is current time in exchange timezone
            snapshot_time = datetime.now(ZoneInfo(tz_name))
            snapshot_time_str = snapshot_time.strftime("%H:%M:%S")
            price_source = "BAR"
            # IVR-001-BUG-4-SUB-1: streaming mode + poll-loop (replaces invalid snapshot+generic-tick pattern)
            _iv_raw_from_mktdata = _fetch_iv_streaming(ib, contract)

        # --- PE-42 Change 5: Write flat metric components to metrics dict ---
        # These are consumed by output.py (_assemble_output) for Data_Basis construction
        # and by transform.py for the restructured output mapping.
        metrics["Live_Price"] = live_price if not math.isnan(live_price) else None
        metrics["Bar_Close_Price"] = actual_price  # always the completed bar close
        metrics["Price_Source"] = price_source
        metrics["Snapshot_Time"] = snapshot_time_str
        metrics["Bar_Range"] = bar_range_str  # e.g. "13:00-14:00" for Profile A, None for B/C
        metrics["Session_Volume"] = _session_vol if p_code == "A" else None  # VOL-004: cumulative session volume (Profile A only)
        metrics["_tz_label"] = tz_label  # internal: used by output.py for Data_Basis construction

        # --- VOL-001: reqHistogramData (Volume Profile) ---
        _hist_fallback = {"A": ["3 days", "1 week"], "B": ["3 weeks", "1 month"], "C": ["3 months"]}
        _hist_periods = _hist_fallback.get(p_code, ["1 month"])
        histogram_data = None
        _hist_period_used = _hist_periods[0]
        for _hp in _hist_periods:
            try:
                histogram_data = ib.reqHistogramData(contract, True, _hp)
                _hist_period_used = _hp
                break
            except Exception:
                continue
        metrics["_histogram_data"] = histogram_data
        metrics["Vol_Histogram_Period"] = _hist_period_used

        # --- IVR-001: Convert raw IV from reqMktData to annualised % ---
        # _iv_raw_from_mktdata is a decimal (e.g. 0.30 = 30%) or None/NaN.
        # Guard: None, NaN, 0, negative, or >500% → set to None.
        HV_LOOKBACK_DAYS = 30
        _iv_current = None
        _raw_iv_val = _iv_raw_from_mktdata
        if (_raw_iv_val is not None
                and not (isinstance(_raw_iv_val, float) and math.isnan(_raw_iv_val))
                and 0 < _raw_iv_val <= 5.0):
            _iv_current = round(_raw_iv_val * 100, 2)  # decimal → annualised %

        # --- IVR-001: 30-Day Historical Volatility from df_ctx ---
        # Log returns of df_ctx closes, std dev, annualise with profile-appropriate factor.
        # BUG-IVR-3: annualization factor must match df_ctx bar frequency:
        #   Profile A (daily bars)   → sqrt(252)
        #   Profile B (weekly bars)  → sqrt(52)
        #   Profile C (monthly bars) → sqrt(12)
        # Guard: fewer than 10 bars → None.
        _HV_ANNUALIZATION_FACTOR = {'A': 252, 'B': 52, 'C': 12}
        _ann_factor = _HV_ANNUALIZATION_FACTOR.get(p_code, 252)
        _hv_30d = None
        if df_ctx is not None and 'close' in df_ctx.columns and len(df_ctx) >= 10:
            _hv_closes = df_ctx['close'].dropna()
            if len(_hv_closes) >= 10:
                _hv_log_returns = np.log(_hv_closes / _hv_closes.shift(1)).dropna()
                _hv_lookback = min(HV_LOOKBACK_DAYS, len(_hv_log_returns))
                _hv_recent = _hv_log_returns.iloc[-_hv_lookback:]
                _hv_30d = round(float(_hv_recent.std() * np.sqrt(_ann_factor)) * 100, 2)

        metrics["IV_Current"] = _iv_current
        metrics["HV_30D"] = _hv_30d

        # --- IB DISCONNECT ---
        if ib.isConnected():
            ib.disconnect()

        # --- POPULATE raw_metrics ---
        raw["is_etf"] = is_etf
        raw["_is_lse_etf"] = _is_lse_etf
        raw["etf_detection_source"] = _etf_detection_source
        raw["etf_primary_exchange"] = _etf_primary_exchange
        raw["clean_ticker"] = clean_ticker
        raw["currency"] = currency
        raw["exchange"] = exchange
        raw["p_exchange"] = p_exchange
        raw["metrics"] = metrics
        raw["adx_col"] = adx_col
        raw["dmp_col"] = dmp_col
        raw["dmn_col"] = dmn_col
        raw["adx_t"] = adx_t
        raw["adx_t1"] = adx_t1
        raw["adx_t2"] = adx_t2
        raw["di_plus"] = di_plus
        raw["di_minus"] = di_minus
        raw["adx_accel"] = adx_accel
        raw["adx_accel_state"] = adx_accel_state
        raw["ma_squeeze"] = ma_squeeze
        raw["resistance_raw"] = resistance_raw
        raw["price_scaler"] = price_scaler
        raw["actual_price"] = actual_price
        raw["atr_raw"] = atr_raw
        raw["structural_floor_raw"] = structural_floor_raw
        raw["hard_stop_raw"] = hard_stop_raw
        raw["_ssg_adjusted"] = _ssg_adjusted
        raw["_ssg_original_raw"] = _ssg_original_raw
        raw["_ssg_reason"] = _ssg_reason
        raw["bars_per_day"] = bars_per_day
        raw["vwap_col"] = vwap_col
        raw["df_ctx"] = df_ctx

        # PA-001: Daily protective values (Profile A only; 0.0 for other profiles)
        raw["Daily_Protective_Anchor"] = daily_ema21
        raw["Daily_ATR"] = daily_atr_val
        raw["Daily_Hard_Stop"] = daily_hard_stop
        raw["Daily_RSI"] = daily_rsi  # PA-001 DQ-8: Daily RSI(14) advisory

        # PA-001 Phase 2: Surface daily protective values into metrics dict
        # so they reach flat_metrics for transform.py mapping.
        # (raw top-level → ctx fields via main.py, but metrics sub-dict is separate)
        metrics["Daily_Protective_Anchor"] = daily_ema21
        metrics["Daily_ATR"] = daily_atr_val
        metrics["Daily_Hard_Stop"] = daily_hard_stop
        metrics["Daily_RSI"] = daily_rsi

        # --- PE-42: New raw metrics for live price supplement ---
        raw["live_price"] = live_price if not math.isnan(live_price) else None
        raw["bar_close_price"] = actual_price  # always completed bar close
        raw["price_source"] = price_source
        raw["snapshot_time"] = snapshot_time_str
        raw["tz_label"] = tz_label
        raw["bar_range"] = bar_range_str  # e.g. "13:00-14:00" for Profile A, None for B/C
        raw["session_volume"] = _session_vol if p_code == "A" else None  # VOL-004

        return df, raw

    except Exception as e:
        import traceback
        if ib.isConnected():
            ib.disconnect()
        raw["_early_return"] = ("ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}", {})
        return None, raw

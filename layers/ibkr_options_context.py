import json
import os
import argparse
import math
import time
from datetime import datetime, date, timedelta
from ib_insync import IB, Stock, Contract, util
import asyncio

# TBS OPTIONS CONTEXT (Module K + OPEX-001) v1.0
# Post-engine informational overlay -- zero engine interaction
# [ModK-OPEX001-SPEC-v1.0]
#
# Module K: Put wall, call wall, max pain, PCR from IBKR options chain.
# OPEX-001: Three-tier calendar classification + advisory text.
#
# Usage:
#   python ibkr_options_context.py AAPL --mode INFO
#   python ibkr_options_context.py AAPL --mode INFO --raw


# ==============================================================================
# CONSTANTS
# ==============================================================================

ILLIQUIDITY_THRESHOLD = 100       # Min put OI at any single strike (spec S3.4)
MONTHLY_GUARD_DAYS = 45           # Max calendar days to next monthly (spec S3.3)
IBKR_PACING_DELAY = 0.22         # ~50 requests per 10 seconds (spec S3.2)
CONNECTION_TIMEOUT = 30           # Seconds before IBKR timeout (spec S7)
ATR_PROXIMITY_THRESHOLD = 0.5    # ATR threshold for floor/ceiling notes (spec S3.8)

PCR_THRESHOLDS = [
    (1.3, "EXTREME BEARISH"),
    (1.0, "BEARISH"),
    (0.7, "NEUTRAL"),
]
PCR_DEFAULT_LABEL = "BULLISH"     # PCR < 0.7

# Holiday dates where third Friday is a market holiday and expiration shifts
# to Thursday. Static list for v1.0 per spec S4.1 TODO.
# TODO: Replace with IBKR trading calendar query for production robustness.
HOLIDAY_SHIFTED_EXPIRATIONS = {
    # Good Friday closures (known US market holidays)
    date(2026, 4, 3): date(2026, 4, 2),   # Good Friday 2026 -> Thursday
    date(2027, 3, 26): date(2027, 3, 25),  # Good Friday 2027 -> Thursday
}

QUARTERLY_MONTHS = {3, 6, 9, 12}


# ==============================================================================
# OPEX CALENDAR LOGIC (spec S4.1)
# ==============================================================================

def _third_friday(year, month):
    """Compute the third Friday of a given month.

    Algorithm per spec S3.3: find first Friday of month, add 14 days.
    """
    first_day = date(year, month, 1)
    # weekday(): Monday=0 ... Friday=4
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    return first_friday + timedelta(days=14)


def _is_third_friday(d):
    """Check if a date is the third Friday of its month."""
    return d == _third_friday(d.year, d.month)


def _classify_opex(today=None):
    """Classify today's OPEX tier per spec S4.1.

    Returns: (opex_flag, opex_tier, is_holiday_shifted)
    """
    if today is None:
        today = date.today()

    # Check if today is a holiday-shifted expiration (Thursday before a Good Friday)
    for holiday_friday, shifted_thursday in HOLIDAY_SHIFTED_EXPIRATIONS.items():
        if today == shifted_thursday:
            month = holiday_friday.month
            if _is_third_friday(holiday_friday):
                if month in QUARTERLY_MONTHS:
                    return True, "QUARTERLY_WITCHING", True
                else:
                    return True, "MONTHLY", True
            else:
                return True, "WEEKLY", True

    # Standard Friday check
    if today.weekday() != 4:  # Not a Friday
        return False, "NONE", False

    # Friday -- determine tier
    if _is_third_friday(today):
        if today.month in QUARTERLY_MONTHS:
            return True, "QUARTERLY_WITCHING", False
        else:
            return True, "MONTHLY", False
    else:
        return True, "WEEKLY", False


def _build_opex_advisory(opex_tier, opex_afternoon, max_pain_distance=None,
                         max_pain_strike=None, opex_flag=True):
    """Construct OPEX advisory text per spec S4.2-4.3.

    Returns: (advisory_text, max_pain_note)
    """
    if not opex_flag or opex_tier == "NONE":
        return "", ""

    # Tier-specific advisory (spec S4.2 -- exact wording)
    if opex_tier == "QUARTERLY_WITCHING":
        advisory = (
            "OPEX ADVISORY (Quarterly/Witching): Quarterly options expiration today. "
            "Maximum gamma hedging and dealer rebalancing expected. "
            "Consider morning execution window. "
            "Intraday volatility historically elevated."
        )
    elif opex_tier == "MONTHLY":
        advisory = (
            "OPEX ADVISORY (Monthly): Monthly options expiration today. "
            "Gamma hedging intensifies into close. "
            "Consider morning execution window."
        )
    elif opex_tier == "WEEKLY":
        advisory = (
            "OPEX ADVISORY (Weekly): Weekly options expiration today. "
            "Muted effect relative to monthly/quarterly. "
            "Note for timing awareness."
        )
    else:
        advisory = ""

    # Afternoon flag (spec S4.2)
    if opex_afternoon:
        advisory += (
            " Afternoon session -- increased pin risk near max pain. "
            "Consider delaying new entries to next trading day."
        )

    # Max pain integration (spec S4.3)
    max_pain_note = ""
    if max_pain_distance is not None and max_pain_strike is not None:
        abs_dist = abs(max_pain_distance)
        if abs_dist <= ATR_PROXIMITY_THRESHOLD:
            max_pain_note = (
                "Current price within %.1f ATR of max pain ($%.2f). Pin risk elevated."
                % (abs_dist, max_pain_strike)
            )
        elif max_pain_distance > 1.0:
            max_pain_note = (
                "Price %.1f ATR above max pain. "
                "Gravitational pull may create downward pressure into expiration."
                % max_pain_distance
            )
        elif max_pain_distance < -1.0:
            max_pain_note = (
                "Price %.1f ATR below max pain. "
                "Gravitational pull supports long thesis into expiration."
                % abs_dist
            )

    return advisory, max_pain_note


# ==============================================================================
# OPEX AFTERNOON CHECK
# ==============================================================================

def _is_afternoon_et():
    """Check if current time is after 12:00 ET.

    Uses a simple UTC-4 (EDT) / UTC-5 (EST) heuristic.
    For production, consider pytz or zoneinfo.
    """
    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        return now_et.hour >= 12
    except ImportError:
        # Fallback: assume UTC-4 (EDT, valid Mar-Nov)
        utc_now = datetime.utcnow()
        et_hour = (utc_now.hour - 4) % 24
        return et_hour >= 12


# ==============================================================================
# MODULE K: IBKR OPTIONS CHAIN LOGIC
# ==============================================================================

def _find_nearest_monthly(expirations, today=None):
    """Select nearest monthly expiration >= today within 45-day guard.

    Args:
        expirations: List of expiration date strings from IBKR (YYYYMMDD format).
        today: Override for testing.

    Returns: (expiry_date_str, expiry_date_obj) or (None, None) with diagnostic.
    """
    if today is None:
        today = date.today()

    monthly_dates = []
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(str(exp_str), "%Y%m%d").date()
        except (ValueError, TypeError):
            continue

        if exp_date < today:
            continue

        if _is_third_friday(exp_date):
            monthly_dates.append((exp_str, exp_date))

    if not monthly_dates:
        return None, None

    # Sort by date, pick nearest
    monthly_dates.sort(key=lambda x: x[1])
    nearest_str, nearest_date = monthly_dates[0]

    # 45-day guard (spec S3.3)
    if (nearest_date - today).days > MONTHLY_GUARD_DAYS:
        return None, None

    return nearest_str, nearest_date


def _compute_max_pain(strikes, put_oi_map, call_oi_map, current_price):
    """Compute max pain strike per spec S3.5.

    Max pain = strike S that minimizes total ITM pain.
    """
    if not strikes:
        return None

    min_pain = None
    max_pain_strike = None

    for s in strikes:
        total_pain = 0.0

        # Put pain: for every put with strike K > S (put is ITM at expiry if underlying = S)
        for k in strikes:
            if k > s:
                oi = put_oi_map.get(k, 0)
                total_pain += (k - s) * oi

        # Call pain: for every call with strike K < S (call is ITM at expiry if underlying = S)
        for k in strikes:
            if k < s:
                oi = call_oi_map.get(k, 0)
                total_pain += (s - k) * oi

        if min_pain is None or total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = s
        elif total_pain == min_pain:
            # Tie-break: nearest to current price (spec S3.5)
            if abs(s - current_price) < abs(max_pain_strike - current_price):
                max_pain_strike = s

    return max_pain_strike


def _compute_wall(oi_map, current_price):
    """Find the strike with maximum OI, tie-break nearest to current price (spec S3.6)."""
    if not oi_map:
        return None, 0

    max_oi = max(oi_map.values())
    candidates = [k for k, v in oi_map.items() if v == max_oi]

    # Tie-break: nearest to current_price
    best = min(candidates, key=lambda k: abs(k - current_price))
    return best, max_oi


def _compute_pcr(total_put_vol, total_call_vol):
    """Compute PCR per spec S3.7.

    Returns: (pcr_value, pcr_label, diagnostic)
    """
    if total_call_vol == 0:
        return None, None, "Zero call volume -- PCR undefined."

    pcr = total_put_vol / total_call_vol

    # Label assignment
    label = PCR_DEFAULT_LABEL
    for threshold, lbl in PCR_THRESHOLDS:
        if pcr > threshold:
            label = lbl
            break

    return round(pcr, 4), label, None


def _compute_trading_dte(expiry_date, today=None):
    """Approximate trading days until expiration (weekdays only)."""
    if today is None:
        today = date.today()
    count = 0
    d = today
    while d < expiry_date:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            count += 1
    return count


# ==============================================================================
# SAFE CONVERSION HELPERS
# ==============================================================================

def _safe_int(val):
    """Convert a value to int, returning 0 for None, NaN, or negative."""
    if val is None:
        return 0
    try:
        if math.isnan(val):
            return 0
    except (TypeError, ValueError):
        return 0
    try:
        result = int(val)
        return max(result, 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _read_oi_from_tickers(ib, all_opt_contracts):
    """Read OI and volume from ticker objects after a wait period.

    Args:
        ib: Connected IB instance.
        all_opt_contracts: List of (contract, strike, right) tuples.

    Returns:
        (put_oi_map, call_oi_map, total_put_vol, total_call_vol, strikes_with_data)
    """
    put_oi_map = {}
    call_oi_map = {}
    total_put_vol = 0
    total_call_vol = 0
    strikes_with_data = 0

    for c, strike, right in all_opt_contracts:
        td = ib.ticker(c)
        _oi = 0
        _vol = 0
        if td is not None:
            _oi = max(
                _safe_int(getattr(td, 'putOpenInterest', None)),
                _safe_int(getattr(td, 'callOpenInterest', None))
            )
            _vol = _safe_int(getattr(td, 'volume', None))
        if _oi > 0:
            strikes_with_data += 1
        if right == "P":
            put_oi_map[strike] = _oi
            total_put_vol += _vol
        else:
            call_oi_map[strike] = _oi
            total_call_vol += _vol

    return put_oi_map, call_oi_map, total_put_vol, total_call_vol, strikes_with_data


# ==============================================================================
# PUBLIC INTERFACE (spec S5.3)
# ==============================================================================

def get_options_context(ticker, current_price, atr_14,
                        mode="INFO", ib_connection=None):
    """Fetch Module K options context + OPEX calendar for a ticker.

    This is the single public interface consumed by the orchestrator.
    Returns a dict with all Options_* and OPEX_* fields per spec S3.9 and S4.4.

    Args:
        ticker: Underlying symbol (e.g. "AAPL").
        current_price: Latest price from engine metrics.
        atr_14: 14-period ATR from engine metrics.
        mode: "INFO" (paper port 4002) or "LIVE" (port 4001).
        ib_connection: Optional existing IB connection (not used -- SRP DQ-K1
                       mandates standalone connection, but reserved for future).

    Returns:
        dict with all Options_* and OPEX_* fields.
    """

    # --- Initialize result dict with defaults ---
    result = {
        # Module K fields (spec S3.9)
        "Options_Put_Wall": None,
        "Options_Put_Wall_OI": None,
        "Options_Put_Wall_Distance": None,
        "Options_Put_Wall_Note": "",
        "Options_Call_Wall": None,
        "Options_Call_Wall_OI": None,
        "Options_Call_Wall_Distance": None,
        "Options_Call_Wall_Note": "",
        "Options_Max_Pain": None,
        "Options_Max_Pain_Distance": None,
        "Options_PCR": None,
        "Options_PCR_Label": None,
        "Options_Expiry_Date": None,
        "Options_Expiry_DTE": None,
        "Options_Status": "UNAVAILABLE",
        "Options_Diagnostic": "",
        # OPEX fields (spec S4.4)
        "OPEX_Flag": False,
        "OPEX_Tier": "NONE",
        "OPEX_Advisory": "",
        "OPEX_Max_Pain_Note": "",
        "OPEX_Afternoon_Flag": False,
    }

    # --- OPEX calendar (always computed -- zero IBKR dependency, spec S7) ---
    opex_flag, opex_tier, _holiday_shifted = _classify_opex()
    result["OPEX_Flag"] = opex_flag
    result["OPEX_Tier"] = opex_tier

    afternoon_flag = False
    if opex_flag:
        afternoon_flag = _is_afternoon_et()
        result["OPEX_Afternoon_Flag"] = afternoon_flag

    # --- Module K: IBKR chain fetch ---
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # SRP (DQ-K1): standalone connection, separate from asset gates
    unique_client_id = 200 + (os.getpid() % 50)  # Range 200-249
    port = 4002 if mode.upper() == "INFO" else 4001
    ib = IB()

    try:
        ib.connect('127.0.0.1', port, clientId=unique_client_id, timeout=CONNECTION_TIMEOUT)

        # Options chain fetch uses DELAYED_FROZEN regardless of mode.
        # We only need OI and volume -- not live pricing or greeks.
        # REALTIME triggers IBKR model computation per strike which floods
        # Gateway logs with "Model is not valid" errors on deep ITM/OTM strikes.
        ib.reqMarketDataType(4)  # DELAYED_FROZEN for OI/volume only

        # --- Contract resolution ---
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
                exchange = route['exchange']
                currency = route['currency']
                p_exchange = route['primary']
                break

        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)
        details = ib.reqContractDetails(contract)

        if not details:
            result["Options_Diagnostic"] = "No contract details found for '%s'." % ticker
            _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
            return result

        resolved = details[0].contract
        con_id = resolved.conId

        # --- Expiration cycle selection (spec S3.3) ---
        chains = ib.reqSecDefOptParams(
            underlyingSymbol=clean_ticker,
            futFopExchange="",
            underlyingSecType="STK",
            underlyingConId=con_id
        )

        if not chains:
            result["Options_Diagnostic"] = "No options chain available for '%s'." % ticker
            _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
            return result

        # Collect all expirations across exchanges
        all_expirations = set()
        all_strikes = set()
        opt_exchange = None
        for ch in chains:
            all_expirations.update(ch.expirations)
            if ch.exchange == "SMART" or opt_exchange is None:
                opt_exchange = ch.exchange
                all_strikes.update(ch.strikes)

        expiry_str, expiry_date = _find_nearest_monthly(all_expirations)

        if expiry_str is None:
            result["Options_Diagnostic"] = "No monthly expiration within 45 days."
            _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
            return result

        result["Options_Expiry_Date"] = "%s-%s-%s" % (expiry_str[:4], expiry_str[4:6], expiry_str[6:])
        result["Options_Expiry_DTE"] = _compute_trading_dte(expiry_date)

        # --- Chain fetch: streaming subscribe-wait-read approach ---
        #
        # reqTickers (snapshot) blocks until IBKR completes model computation,
        # which hangs indefinitely after hours when the model notifier loops.
        #
        # Instead: subscribe all contracts at once via reqMktData (streaming),
        # wait a fixed period for OI data to arrive, read it, cancel.
        # This never blocks and works at any time of day.
        #
        # Strike filter: $5 increments only. reqSecDefOptParams returns strikes
        # from all expirations (weekly $1/$2.50 + monthly $5). Filtering to
        # % 5 == 0 keeps only standard monthly strikes.
        sorted_strikes = sorted(all_strikes)
        _lo = current_price * 0.80
        _hi = current_price * 1.20
        filtered_strikes = [
            s for s in sorted_strikes
            if _lo <= s <= _hi and s % 5 == 0
        ]
        if not filtered_strikes:
            # Fallback: try $1 increments in tighter range
            filtered_strikes = [
                s for s in sorted_strikes
                if current_price * 0.90 <= s <= current_price * 1.10
            ]
        if not filtered_strikes:
            result["Options_Diagnostic"] = (
                "No standard strikes found for '%s' in range $%.0f-$%.0f."
                % (ticker, _lo, _hi)
            )
            _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
            return result

        _opt_exch = opt_exchange or "SMART"

        # =================================================================
        # CHAIN FETCH: Streaming with generic tick 101 (OI)
        #
        # Generic tick 101 = Option Open Interest. Without it, OI fields
        # do not populate in the streaming tick set for options.
        #
        # Fallback: if streaming returns no data, re-subscribe with
        # snapshot=True (non-blocking) + fixed wait. This avoids
        # reqTickers which hangs on Windows after hours because the
        # model notifier never completes and RequestTimeout doesn't
        # reliably interrupt GetQueuedCompletionStatus.
        # =================================================================

        # Step 1: Build contract list
        all_opt_contracts = []  # (contract, strike, right)
        for strike in filtered_strikes:
            for right in ("P", "C"):
                c = Contract()
                c.symbol = clean_ticker
                c.secType = "OPT"
                c.exchange = _opt_exch
                c.currency = currency
                c.lastTradeDateOrContractMonth = expiry_str
                c.strike = strike
                c.right = right
                all_opt_contracts.append((c, strike, right))

        # Step 2: Subscribe all with generic tick 101 (OI), streaming mode
        for c, _, _ in all_opt_contracts:
            ib.reqMktData(c, '100,101', False, False)

        ib.sleep(8)

        put_oi_map, call_oi_map, total_put_vol, total_call_vol, _strikes_with_data = \
            _read_oi_from_tickers(ib, all_opt_contracts)

        # Cancel streaming subscriptions
        for c, _, _ in all_opt_contracts:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass

        # Step 3: Fallback if streaming returned no OI.
        # Re-subscribe in snapshot mode (non-blocking) without generic ticks.
        # Snapshot mode delivers a full tick bundle including OI. We don't
        # use reqTickers (it blocks until snapshot completes, which hangs
        # after hours on Windows). Instead, reqMktData with snapshot=True
        # returns immediately -- we read after a fixed wait.
        _used_fallback = False
        if _strikes_with_data == 0:
            _used_fallback = True

            for c, _, _ in all_opt_contracts:
                ib.reqMktData(c, '', True, False)  # snapshot=True, non-blocking

            ib.sleep(12)  # Longer wait for snapshot delivery after hours

            put_oi_map, call_oi_map, total_put_vol, total_call_vol, _strikes_with_data = \
                _read_oi_from_tickers(ib, all_opt_contracts)

            # No cancel needed -- snapshot subscriptions auto-close

        # Step 4: Partial-data quality check
        _total_contracts = len(all_opt_contracts)
        _data_pct = (_strikes_with_data / _total_contracts * 100) if _total_contracts > 0 else 0
        _partial_data_warning = ""
        if 0 < _data_pct < 30:
            _partial_data_warning = (
                "Partial data: only %d/%d contracts (%d%%) returned OI. "
                "Data may be incomplete."
                % (_strikes_with_data, _total_contracts, int(_data_pct))
            )
        if _used_fallback and _strikes_with_data > 0:
            _fb_note = "Snapshot fallback used (after-hours or slow Gateway)."
            _partial_data_warning = (
                "%s %s" % (_partial_data_warning, _fb_note)
            ).strip()

        # --- Illiquidity guard (spec S3.4) ---
        max_put_oi = max(put_oi_map.values()) if put_oi_map else 0
        if max_put_oi < ILLIQUIDITY_THRESHOLD:
            result["Options_Diagnostic"] = (
                "Options chain illiquid (max put OI: %d). Options context unavailable."
                % max_put_oi
            )
            _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
            return result

        # --- Computations ---
        # Put wall (spec S3.6)
        put_wall_strike, put_wall_oi = _compute_wall(put_oi_map, current_price)
        result["Options_Put_Wall"] = put_wall_strike
        result["Options_Put_Wall_OI"] = put_wall_oi

        # Call wall (spec S3.6)
        call_wall_strike, call_wall_oi = _compute_wall(call_oi_map, current_price)
        result["Options_Call_Wall"] = call_wall_strike
        result["Options_Call_Wall_OI"] = call_wall_oi

        # Max pain (spec S3.5)
        all_chain_strikes = sorted(set(list(put_oi_map.keys()) + list(call_oi_map.keys())))
        max_pain = _compute_max_pain(all_chain_strikes, put_oi_map, call_oi_map, current_price)
        result["Options_Max_Pain"] = max_pain

        # PCR (spec S3.7)
        pcr_val, pcr_label, pcr_diag = _compute_pcr(total_put_vol, total_call_vol)
        result["Options_PCR"] = pcr_val
        result["Options_PCR_Label"] = pcr_label

        # ATR distance computation (spec S3.8)
        if atr_14 and atr_14 > 0:
            # Put wall distance: (current_price - put_wall) / ATR_14
            # Positive = price above wall (safe)
            if put_wall_strike is not None:
                pw_dist = round((current_price - put_wall_strike) / atr_14, 2)
                result["Options_Put_Wall_Distance"] = pw_dist
                if abs(pw_dist) <= ATR_PROXIMITY_THRESHOLD:
                    result["Options_Put_Wall_Note"] = (
                        "FLOOR REINFORCEMENT -- Put wall at $%.2f reinforces the structural floor."
                        % put_wall_strike
                    )

            # Call wall distance: (call_wall - current_price) / ATR_14
            # Positive = wall above price (room to ceiling)
            if call_wall_strike is not None:
                cw_dist = round((call_wall_strike - current_price) / atr_14, 2)
                result["Options_Call_Wall_Distance"] = cw_dist
                if abs(cw_dist) <= ATR_PROXIMITY_THRESHOLD:
                    result["Options_Call_Wall_Note"] = (
                        "CEILING PRESSURE -- Call wall at $%.2f reinforces the structural ceiling."
                        % call_wall_strike
                    )

            # Max pain distance: (current_price - max_pain) / ATR_14
            # Positive = price above max pain
            if max_pain is not None:
                mp_dist = round((current_price - max_pain) / atr_14, 2)
                result["Options_Max_Pain_Distance"] = mp_dist

        # Handle zero call volume PCR (spec S3.7 / S7: partial availability)
        if pcr_diag:
            # PCR is UNAVAILABLE but other metrics are fine
            result["Options_PCR"] = None
            result["Options_PCR_Label"] = None
            # Note: per spec S7 "Zero call volume" row -- put wall, call wall,
            # max pain computed normally. Only PCR = UNAVAILABLE.
            # Options_Status remains AVAILABLE; diagnostic appended for PCR only.
            result["Options_Status"] = "AVAILABLE"
            _diag_parts = [pcr_diag]
            if _partial_data_warning:
                _diag_parts.append(_partial_data_warning)
            result["Options_Diagnostic"] = " ".join(_diag_parts)
        else:
            result["Options_Status"] = "AVAILABLE"
            result["Options_Diagnostic"] = _partial_data_warning  # Empty if data was clean

        # --- OPEX max pain integration (spec S4.3) ---
        _finalize_opex(result, opex_flag, opex_tier, afternoon_flag,
                        max_pain_distance=result.get("Options_Max_Pain_Distance"),
                        max_pain_strike=result.get("Options_Max_Pain"))

        return result

    except ConnectionRefusedError:
        result["Options_Diagnostic"] = "IBKR connection failed. Options context unavailable."
        _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
        return result
    except asyncio.TimeoutError:
        result["Options_Diagnostic"] = "IBKR timeout (%ds). Options context unavailable." % CONNECTION_TIMEOUT
        _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
        return result
    except Exception as e:
        result["Options_Diagnostic"] = "IBKR error: %s. Options context unavailable." % str(e)[:80]
        _finalize_opex(result, opex_flag, opex_tier, afternoon_flag)
        return result
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def _finalize_opex(result, opex_flag, opex_tier, afternoon_flag,
                   max_pain_distance=None, max_pain_strike=None):
    """Build OPEX advisory fields and merge into result dict."""
    advisory, mp_note = _build_opex_advisory(
        opex_tier, afternoon_flag,
        max_pain_distance=max_pain_distance,
        max_pain_strike=max_pain_strike,
        opex_flag=opex_flag
    )
    result["OPEX_Advisory"] = advisory
    result["OPEX_Max_Pain_Note"] = mp_note


# ==============================================================================
# CLI DASHBOARD OUTPUT
# ==============================================================================

def _format_dashboard(result, ticker, current_price):
    """Format Module K + OPEX data as a human-readable dashboard."""
    lines = []
    status = result.get("Options_Status", "UNAVAILABLE")

    lines.append("--- OPTIONS CONTEXT ---")

    if status == "AVAILABLE":
        # Put wall
        pw = result.get("Options_Put_Wall")
        pw_oi = result.get("Options_Put_Wall_OI")
        pw_dist = result.get("Options_Put_Wall_Distance")
        pw_note = result.get("Options_Put_Wall_Note", "")
        pw_line = "Put Wall:      $%.2f (OI: %s)" % (pw, "{:,}".format(pw_oi) if pw_oi else "N/A")
        if pw_dist is not None:
            pw_line += "  |  Distance: %+.1f ATR" % pw_dist
        if pw_note:
            pw_line += "  |  FLOOR REINFORCEMENT"
        lines.append(pw_line)

        # Call wall
        cw = result.get("Options_Call_Wall")
        cw_oi = result.get("Options_Call_Wall_OI")
        cw_dist = result.get("Options_Call_Wall_Distance")
        cw_note = result.get("Options_Call_Wall_Note", "")
        cw_line = "Call Wall:     $%.2f (OI: %s)" % (cw, "{:,}".format(cw_oi) if cw_oi else "N/A")
        if cw_dist is not None:
            cw_line += "  |  Distance: %+.1f ATR" % cw_dist
        if cw_note:
            cw_line += "  |  CEILING PRESSURE"
        lines.append(cw_line)

        # Max pain
        mp = result.get("Options_Max_Pain")
        mp_dist = result.get("Options_Max_Pain_Distance")
        mp_line = "Max Pain:      $%.2f" % mp if mp else "Max Pain:      N/A"
        if mp_dist is not None:
            mp_line += "               |  Distance: %+.1f ATR" % mp_dist
        lines.append(mp_line)

        # PCR
        pcr = result.get("Options_PCR")
        pcr_label = result.get("Options_PCR_Label")
        if pcr is not None:
            lines.append("PCR:           %.2f (%s)" % (pcr, pcr_label))
        else:
            _pcr_diag = result.get("Options_Diagnostic", "")
            if "Zero call volume" in _pcr_diag:
                lines.append("PCR:           UNAVAILABLE (%s)" % _pcr_diag)
            else:
                lines.append("PCR:           UNAVAILABLE")

        # Expiry
        exp_date = result.get("Options_Expiry_Date", "N/A")
        exp_dte = result.get("Options_Expiry_DTE", "N/A")
        lines.append("Expiry:        %s (%s trading days)" % (exp_date, exp_dte))

        # Partial data warning (if present)
        _diag = result.get("Options_Diagnostic", "")
        if "Partial data" in _diag:
            lines.append("WARNING:       %s" % _diag)

    else:
        # UNAVAILABLE
        lines.append("Status:        UNAVAILABLE")
        diag = result.get("Options_Diagnostic", "")
        if diag:
            lines.append("Diagnostic:    %s" % diag)

    # OPEX advisory (spec S4.5)
    if result.get("OPEX_Flag"):
        lines.append("")
        lines.append("--- OPEX ADVISORY ---")
        _tier_display_map = {
            "QUARTERLY_WITCHING": "OPEX (Quarterly/Witching)",
            "MONTHLY": "OPEX (Monthly)",
            "WEEKLY": "OPEX (Weekly)",
        }
        tier_display = _tier_display_map.get(result.get("OPEX_Tier", "NONE"), "NONE")
        lines.append("Tier:          %s" % tier_display)

        advisory = result.get("OPEX_Advisory", "")
        if advisory:
            # Wrap long advisory text
            lines.append("Advisory:      %s" % advisory)

        mp_note = result.get("OPEX_Max_Pain_Note", "")
        if mp_note:
            lines.append("Max Pain:      %s" % mp_note)

        if result.get("OPEX_Afternoon_Flag"):
            lines.append("Afternoon:     Afternoon session -- increased pin risk. Consider delaying new entries.")

    return "\n".join(lines)


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBS Options Context (Module K + OPEX-001) -- Post-engine informational overlay"
    )
    parser.add_argument("ticker",
                        help="Underlying symbol (e.g. AAPL, MSFT, SPY)")
    parser.add_argument("--mode", default="INFO",
                        choices=["INFO", "LIVE"],
                        help="INFO (paper port 4002) or LIVE (port 4001)")
    parser.add_argument("--price", type=float, default=None,
                        help="Override current price (default: fetched from IBKR via contract)")
    parser.add_argument("--atr", type=float, default=None,
                        help="Override ATR_14 value (default: computed from 14-day bars)")
    parser.add_argument("--raw", action="store_true",
                        help="Output raw JSON (orchestrator-compatible) instead of dashboard format")

    args = parser.parse_args()

    # If price/ATR not provided, use reasonable defaults for standalone testing
    _current_price = args.price if args.price else 0.0
    _atr_14 = args.atr if args.atr else 0.0

    # If no price/ATR provided, attempt a quick IBKR fetch for standalone mode
    if _current_price == 0.0 or _atr_14 == 0.0:
        print("[INFO] Price/ATR not provided. Attempting IBKR fetch for standalone context...")
        try:
            _standalone_ib = IB()
            _standalone_port = 4002 if args.mode == "INFO" else 4001
            _standalone_cid = 250 + (os.getpid() % 50)
            _standalone_ib.connect('127.0.0.1', _standalone_port, clientId=_standalone_cid)
            if args.mode == "LIVE":
                _standalone_ib.reqMarketDataType(1)
            else:
                _standalone_ib.reqMarketDataType(4)

            _clean = args.ticker.upper()
            _exch, _curr, _pex = "SMART", "USD", ""
            for _suf, _rte in {'.L': ('SMART','GBP','LSE'), '.TO': ('SMART','CAD','TSE')}.items():
                if _clean.endswith(_suf):
                    _clean = _clean.replace(_suf, '')
                    _exch, _curr, _pex = _rte
                    break
            _sc = Stock(_clean, _exch, _curr, primaryExchange=_pex)
            _bars = _standalone_ib.reqHistoricalData(
                _sc, '', '1 M', '1 day', 'TRADES', True
            )
            if _bars and len(_bars) >= 14:
                import math
                _closes = [b.close for b in _bars]
                _highs = [b.high for b in _bars]
                _lows = [b.low for b in _bars]
                if _current_price == 0.0:
                    _current_price = _closes[-1]
                if _atr_14 == 0.0:
                    # Simple ATR computation
                    _trs = []
                    for i in range(1, len(_closes)):
                        _tr = max(
                            _highs[i] - _lows[i],
                            abs(_highs[i] - _closes[i-1]),
                            abs(_lows[i] - _closes[i-1])
                        )
                        _trs.append(_tr)
                    if len(_trs) >= 14:
                        _atr_14 = round(sum(_trs[-14:]) / 14, 4)
                print("[INFO] Fetched: Price=$%.2f, ATR_14=$%.4f" % (_current_price, _atr_14))
            _standalone_ib.disconnect()
        except Exception as _e:
            print("[WARN] Standalone price/ATR fetch failed: %s" % str(_e)[:60])
            if _current_price == 0.0:
                _current_price = 100.0  # Fallback for ATR computation safety
            if _atr_14 == 0.0:
                _atr_14 = 2.0          # Fallback

    result = get_options_context(args.ticker, _current_price, _atr_14, mode=args.mode)

    if args.raw:
        print(json.dumps(result, indent=4, default=str))
    else:
        print("\n" + "=" * 60)
        print("OPTIONS CONTEXT: %s | Mode: %s" % (args.ticker.upper(), args.mode))
        print("Price: $%.2f | ATR_14: $%.4f" % (_current_price, _atr_14))
        print("=" * 60)
        print(_format_dashboard(result, args.ticker, _current_price))
        print("=" * 60)

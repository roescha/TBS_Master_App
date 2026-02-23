from ib_insync import IB, Stock, util

def verify_asset_type(ticker: str, mode: str = "INFO") -> dict:
    """
    [MANDATE: DOC 8 SEC 23] High-Fidelity Asset Identification.
    Checks deterministic suffixes and IBKR metadata to classify ETFs.
    """
    # Patch asyncio for Windows threading compatibility
    util.patchAsyncio()

    port = 4001 if mode.upper() == "LIVE" else 4002
    ib = IB()

    clean_ticker = ticker.upper()
    is_etf = False
    asset_name = "Unknown"

    # LAYER 1: DETERMINISTIC SUFFIX CHECK
    exchange, currency, p_exchange = 'SMART', 'USD', ""
    routing_map = {
        '.L': {'exch': 'SMART', 'curr': 'GBP', 'prim': 'LSE'},
        '.TO': {'exch': 'SMART', 'curr': 'CAD', 'prim': 'TSE'},
        '.DE': {'exch': 'IBIS', 'curr': 'EUR', 'prim': 'IBIS'},
        '.AS': {'exch': 'AEB', 'curr': 'EUR', 'prim': 'AEB'},
        '.PA': {'exch': 'SBF', 'curr': 'EUR', 'prim': 'SBF'}
    }

    for suffix, route in routing_map.items():
        if clean_ticker.endswith(suffix):
            clean_ticker = clean_ticker.replace(suffix, '')
            exchange, currency, p_exchange = route['exch'], route['curr'], route['prim']
            break

    try:
        # Standard synchronous connection
        ib.connect('127.0.0.1', port, clientId=99)
        contract = Stock(clean_ticker, exchange, currency, primaryExchange=p_exchange)

        # Standard synchronous data request
        details = ib.reqContractDetails(contract)
        if details:
            asset_name = details[0].longName.upper()
            etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS', 'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']

            if any(key in asset_name for key in etf_keywords):
                is_etf = True

    except Exception as e:
        raise Exception(f"IBKR Auto-ID Failure: {str(e)}")
    finally:
        if ib.isConnected():
            ib.disconnect()

    return {
        "ticker": clean_ticker,
        "is_etf": is_etf,
        "asset_name": asset_name,
        "routed_exchange": exchange,
        "currency": currency
    }
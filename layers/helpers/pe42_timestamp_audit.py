#!/usr/bin/env python3
"""
PE-42 Timestamp Audit -- dump raw hourly bar timestamps from IBKR.
Run anytime (market open or closed). Shows last 10 hourly bars.

Usage: python pe42_timestamp_audit.py --port 4001
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ib_insync import IB, Stock, util


def run(port):
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    now_utc = datetime.now(timezone.utc)

    print(f"Wall clock ET:  {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Wall clock UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    ib = IB()
    cid = 250 + (os.getpid() % 50)

    try:
        ib.connect('127.0.0.1', port, clientId=cid)
        ib.reqMarketDataType(1)
    except Exception as e:
        print(f"[FATAL] Cannot connect: {e}")
        sys.exit(1)

    # Test with AAPL (liquid, NASDAQ)
    tickers = [
        ("AAPL", "SMART", "USD", ""),
        ("JPM",  "SMART", "USD", ""),
    ]

    for sym, exch, curr, pexch in tickers:
        contract = Stock(sym, exch, curr, primaryExchange=pexch)
        details = ib.reqContractDetails(contract)
        if details:
            contract = details[0].contract

        print(f"=== {sym} HOURLY (1 hour, 3 M, useRTH=True) ===")
        bars = ib.reqHistoricalData(contract, '', '3 M', '1 hour', 'TRADES', True)
        if bars:
            df = util.df(bars)
            print(f"Total bars: {len(df)}")
            print(f"Last 10 bars (raw 'date' column):")
            for _, row in df.tail(10).iterrows():
                print(f"  date={row['date']}  O={row['open']:.2f}  H={row['high']:.2f}  "
                      f"L={row['low']:.2f}  C={row['close']:.2f}  V={int(row['volume']):,}")
        else:
            print("  NO DATA")

        print()

        print(f"=== {sym} DAILY (1 day, 2 Y, useRTH=True) ===")
        bars_d = ib.reqHistoricalData(contract, '', '10 D', '1 day', 'TRADES', True)
        if bars_d:
            df_d = util.df(bars_d)
            print(f"Last 3 bars (raw 'date' column):")
            for _, row in df_d.tail(3).iterrows():
                print(f"  date={row['date']}  O={row['open']:.2f}  H={row['high']:.2f}  "
                      f"L={row['low']:.2f}  C={row['close']:.2f}  V={int(row['volume']):,}")
        else:
            print("  NO DATA")

        print()

    if ib.isConnected():
        ib.disconnect()

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4001)
    args = parser.parse_args()
    run(args.port)

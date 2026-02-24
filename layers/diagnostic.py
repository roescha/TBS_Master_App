from ib_insync import IB, Stock
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=99)

for ticker in ['VUAG', 'VWRP', 'VUSA', 'ISF']:
    c = Stock(ticker, 'SMART', 'GBP', primaryExchange='LSE')
    d = ib.reqContractDetails(c)
    if d:
        meta = d[0].longName
        conId = d[0].contract.conId
        pExch = getattr(d[0].contract, 'primaryExchange', '') or getattr(d[0], 'primaryExch', '')
        etf_keywords = ['ETF', 'FUND', 'VANGUARD', 'ISHARES', 'UCITS',
                        'SELECT SECTOR', 'SPDR', 'INVESCO', 'SCHWAB', 'PROSHARES']
        matched = [k for k in etf_keywords if k in meta.upper()]
        print(f"{ticker}: longName='{meta}' | conId={conId} | pExch={pExch} | ETF keywords matched: {matched}")
    else:
        print(f"{ticker}: NO DETAILS RETURNED")

ib.disconnect()
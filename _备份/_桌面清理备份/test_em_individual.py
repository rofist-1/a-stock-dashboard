import time, requests as req

session = req.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://quote.eastmoney.com/"})

# Try individual stock API - different endpoint
codes = ["1.600519", "0.300750", "0.000858", "1.688056", "0.301528"]
for secid in codes:
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    try:
        r = session.get(url, params=params, timeout=10)
        print(f"{secid}: status={r.status_code}, text={r.text[:200]}")
    except Exception as e:
        print(f"{secid}: error={e}")
    time.sleep(0.5)

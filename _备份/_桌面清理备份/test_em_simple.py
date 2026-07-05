import requests as req
import time

for secid in ["1.600519", "0.300750", "0.000858"]:
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        r = req.get(url, params=params, headers=headers, timeout=10)
        d = r.json().get("data", {})
        print(f"{secid}: f57={d.get('f57')}, f58={d.get('f58')}, f127={d.get('f127')}")
    except Exception as e:
        print(f"{secid}: error {e}")
    time.sleep(0.3)

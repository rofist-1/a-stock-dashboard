import time

# Method 1: curl_cffi
from curl_cffi import requests as cffi_req
headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}

for secid in ["1.600519", "0.300750", "0.000858"]:
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    try:
        r = cffi_req.get(url, params=params, headers=headers, impersonate="chrome110", timeout=15)
        d = r.json().get("data", {})
        print(f"curl_cffi {secid}: f127={d.get('f127')}")
    except Exception as e:
        print(f"curl_cffi {secid}: {e}")
    time.sleep(0.5)

# Method 2: try with https:// instead of http://
import requests as req
for secid in ["1.600519", "0.300750", "0.000858"]:
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    try:
        r = req.get(url, params=params, headers=headers, timeout=10)
        d = r.json().get("data", {})
        print(f"req {secid}: f127={d.get('f127')}")
    except Exception as e:
        print(f"req {secid}: {e}")
    time.sleep(0.3)

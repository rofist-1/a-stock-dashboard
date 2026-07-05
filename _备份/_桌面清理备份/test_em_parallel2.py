import time, requests as req
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_industry(secid):
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        r = req.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            d = r.json().get("data")
            if d:
                return (d.get("f57"), d.get("f127"))
        return (None, None, f"status={r.status_code}")
    except Exception as e:
        return (None, None, str(e))

codes = [("1.600519","600519"), ("0.300750","300750"), ("0.000858","000858")]
t0 = time.time()
results = {}
with ThreadPoolExecutor(max_workers=3) as pool:
    fut_map = {}
    for secid, code in codes:
        fut_map[pool.submit(get_industry, secid)] = (secid, code)
    for f in as_completed(fut_map):
        secid, code = fut_map[f]
        c, ind, err = f.result()
        if c and ind:
            results[c] = ind
            print(f"  OK {code}: {ind}")
        else:
            print(f"  FAIL {code}: {err}")

print(f"Total: {len(results)}")

import time, requests as req, json
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_industry(secid):
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        r = req.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            d = r.json().get("data", {})
            return (d.get("f57"), d.get("f127"))
    except:
        pass
    return (None, None)

# Test 20 stocks in parallel
codes = [f"1.{c}" for c in ["600519","601318","600036","601166","600276","600887","600900","601012","600309","601899","600585","600104","688111","688981","688599","688056","688777","688322","688668","688059"]]
codes += [f"0.{c}" for c in ["000001","000002","000333","000651","000858","000568","000538","000063","300750","300059","300015","300014","300274","300124","300033","300498","301528","300328","300835","301458"]]

t0 = time.time()
results = {}
with ThreadPoolExecutor(max_workers=10) as pool:
    fut = {pool.submit(get_industry, c): c for c in codes}
    for f in as_completed(fut):
        code, ind = f.result()
        if code and ind:
            results[code] = ind

elapsed = time.time() - t0
print(f"Got {len(results)}/{len(codes)} industries in {elapsed:.1f}s")
codes_with_data = list(results.items())[:10]
for k, v in codes_with_data:
    print(f"  {k}: {v}")

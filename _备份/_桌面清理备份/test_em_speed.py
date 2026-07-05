import time, requests as req

session = req.Session()
session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})

def get_ind(secid, delay=0):
    time.sleep(delay)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": secid, "fields": "f57,f58,f127", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
    try:
        r = session.get(url, params=params, timeout=10)
        if r.status_code == 200:
            d = r.json().get("data")
            if d:
                return d.get("f127")
    except:
        pass
    return None

# Test delays: 0, 0.05, 0.1, 0.2
test_codes = [f"1.{c}" for c in ["600519","601318","600036","601166","600276","600887","600900"]] + [f"0.{c}" for c in ["000001","000002","000333","000858","300750","300059"]]
test_codes_short = test_codes[:5]

for delay in [0, 0.05, 0.1, 0.2]:
    t0 = time.time()
    ok = 0
    fail = 0
    for secid in test_codes:
        ind = get_ind(secid, delay)
        if ind:
            ok += 1
        else:
            fail += 1
    elapsed = time.time() - t0
    print(f"Delay {delay:.2f}s: {ok} ok, {fail} fail in {elapsed:.1f}s")

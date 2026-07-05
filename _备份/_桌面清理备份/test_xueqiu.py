import requests as req

url = "https://stock.xueqiu.com/v5/stock/batch/quote.json?symbol=SZ300750,SZ000858,SH600519&extend=detail"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": "xq_a_token=123",
}
r = req.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if data.get("data") and data["data"].get("items"):
        item = data["data"]["items"][0]
        q = item.get("quote", {})
        print("Keys:", list(q.keys())[:40])
        for k in ["type", "type_name", "industry_code", "industry_name", "sector", "industry", "trade_value"]:
            if k in q:
                print(f"  {k}: {q[k]}")

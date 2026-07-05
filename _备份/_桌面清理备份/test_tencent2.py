import requests

tests = [
    "http://qt.gtimg.cn/q=shhy",
    "http://qt.gtimg.cn/q=szhy",
    "http://qt.gtimg.cn/q=shbk",
    "http://qt.gtimg.cn/q=szbk",
    "http://qt.gtimg.cn/q=r_shindustry",
    "http://qt.gtimg.cn/q=r_szindustry",
    "http://qt.gtimg.cn/q=shgn",
    "http://qt.gtimg.cn/q=szgn",
]

for url in tests:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        r.encoding = "utf-8"
        q = url.split("q=")[1]
        print(f"{q:<20} -> {r.status_code} | {r.text[:120]}")
    except Exception as e:
        q = url.split("q=")[1]
        print(f"{q:<20} -> Error: {e}")

import requests as req
import json

# Tencent individual stock detail page - try to get industry via PC detail
url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz300750,day,,,1,qfq"
r = req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
print("K-line page:", r.status_code)

# Try the individual stock info API from Tencent
url2 = "https://web.ifzg.gtimg.cn/stock/individual/get?symbol=sz300750"
# Actually let me try the stock info endpoint
url3 = "https://proxy.finance.qq.com/stock/individual/get?symbol=sz300750&type=detail"
r3 = req.get(url3, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://stockhtm.finance.qq.com"}, timeout=10)
print(f"Stock detail: {r3.status_code}")
with open("tencent_detail.txt", "w", encoding="utf-8") as f:
    f.write(r3.text[:2000])
print(r3.text[:500])

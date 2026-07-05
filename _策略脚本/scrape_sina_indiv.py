import requests as req
import re

# Try scraping Sina individual stock page for industry info
headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}

# Try a few stocks
stocks = ["sh688056", "sz301528", "sh603135", "sz300328"]
for s in stocks:
    url = f"https://finance.sina.com.cn/realstock/company/{s}/nc.shtml"
    try:
        r = req.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        # Look for industry info in the page
        # Common patterns: "行业", "industry", "板块"
        matches = []
        for pat in ["行业", "板块"]:
            for m in re.finditer(pat + r'.{0,50}', r.text):
                matches.append(m.group())
        if matches:
            print(f"{s}: {matches[:3]}")
        else:
            print(f"{s}: no industry info found")
    except Exception as e:
        print(f"{s}: error {e}")

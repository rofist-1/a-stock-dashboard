import akshare as ak
import time

# Try just ONE sector with delay before
time.sleep(3)
try:
    df = ak.stock_sector_spot()
    print(f"stock_sector_spot OK: {len(df)} rows")
except Exception as e:
    print(f"stock_sector_spot failed: {e}")
    # Try raw URL
    import requests as req
    url = "https://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/sshy/subkind/sshy/index.phtml"
    r = req.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}, timeout=15)
    print(f"Status: {r.status_code}, text: {r.text[:200]}")

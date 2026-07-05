import requests, re

url = 'http://q.10jqka.com.cn/gn/detail/code/301085/'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
r = requests.get(url, headers=headers, timeout=15)
r.encoding = 'utf-8'
text = r.text

# Find JS data in page
# THS typically uses a data-* attribute or JS variable
data_patterns = re.findall(r'(data-config|data-url|ajaxurl|loadurl|boardAjax)', text)
print("Data patterns:", data_patterns[:10])

# Check for JS variables with stock data
stock_vars = re.findall(r'(?:var|let|const)\s+(\w+)\s*=\s*[\"\']?([^\"\';]+)', text)
for name, val in stock_vars[:30]:
    if any(x in val.lower() for x in ['ajax', 'url', 'api', 'load', 'data']):
        print(f"  {name} = {val}")

# Look for script tags and their src
scripts = re.findall(r'<script[^>]*src=[\"\']([^\"\']+)[\"\']', text)
for s in scripts[:20]:
    print(f"  Script: {s}")

# The constituent stock data might be in a JSON API
# THS typically uses: http://q.10jqka.com.cn/gn/detail/code/XXX/ajax/1/
# Or: http://q.10jqka.com.cn/index/index/board/XXX/
print("\n--- Trying AJAX URL ---")
ajax_url = f'http://q.10jqka.com.cn/index/index/board/301085/field/code/order/asc/page/1/ajax/1/'
try:
    r2 = requests.get(ajax_url, headers=headers, timeout=10)
    print(f"AJAX status: {r2.status_code}, len={len(r2.text)}")
    print(r2.text[:500])
except Exception as e:
    print(f"AJAX error: {e}")

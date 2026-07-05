import requests, re, time

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# First get main page to set cookies
r = s.get('http://q.10jqka.com.cn/gn/detail/code/301085/', timeout=15)
print(f"Initial: {r.status_code}, cookies: {dict(s.cookies)}")

# Try AJAX URL with session
ajax_url = 'http://q.10jqka.com.cn/index/index/board/301085/field/code/order/asc/page/1/ajax/1/'
r2 = s.get(ajax_url, timeout=15)
r2.encoding = 'utf-8'
print(f"AJAX: {r2.status_code}, len={len(r2.text)}")
if r2.status_code == 200:
    # Check if HTML or JSON
    if r2.text.strip().startswith('<'):
        # Look for table data
        codes = re.findall(r'<td[^>]*class=[\"\']?\w*code\w*[\"\']?[^>]*>(\d{6})</td>', r2.text)
        print(f"Found {len(codes)} stock codes in table")
        print(codes[:10])
    else:
        print(r2.text[:500])

# Try another URL pattern
alt_url = 'http://q.10jqka.com.cn/gn/detail/code/301085/ajax/1/'
r3 = s.get(alt_url, timeout=15)
r3.encoding = 'utf-8'
print(f"\nAlt URL: {r3.status_code}, len={len(r3.text)}")
print(r3.text[:300])

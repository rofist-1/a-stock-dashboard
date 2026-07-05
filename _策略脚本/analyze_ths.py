import re

with open('C:\\Users\\Rofis\\Desktop\\ths_page.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Look for pagination
pages = re.findall(r'(?:page|Page|p=)(\d+)', text)
print("Page references:", pages)

# Look for URLs with page/ajax/board patterns
urls = re.findall(r'(?:href|src)=["\']([^"\']+)["\']', text)
for u in urls:
    low = u.lower()
    if any(x in low for x in ['ajax', 'page', 'board', 'concept']):
        print(f"  URL: {u}")

# Look for data attributes
data_attrs = re.findall(r'data-(\w+)="([^"]*)"', text)
for k, v in data_attrs:
    print(f"  data-{k} = {v}")

# Check page length
print(f"\nTotal length: {len(text)} bytes")
print(f"Script tags: {len(re.findall(r'<script', text))}")

# Check for the stock table specifically - look for tr with td containing numbers
tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
for i, tr in enumerate(tr_matches[:30]):
    if 'td' in tr.lower() and re.search(r'\d{6}', tr):
        print(f"  TR {i}: {tr[:200]}")

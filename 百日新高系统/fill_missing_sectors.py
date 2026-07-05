import json
import requests

with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'r', encoding='utf-8') as f:
    smap = json.load(f)

# For missing stocks, try to fetch from akshare stock list which has industry
import akshare as ak

# Get all A-stock list with industry from cninfo
try:
    df = ak.stock_info_a_code_name()
    # This only has code+name, not industry
except:
    pass

# Try stock_board_industry_name_em for industry list
# Already confirmed EM is blocked

# Try scraping THS website for individual stock info
# http://basic.10jqka.com.cn/000034/  or similar

headers = {'User-Agent': 'Mozilla/5.0'}

missing = [s for s in data['stocks'] if not (s.get('sector','') or '').strip()]
print(f'Missing: {len(missing)} stocks\n')

# Try to get info from THS (10jqka) basic info page
import re
for s in missing:
    code = s['code'].split('.')[0]
    try:
        url = f'http://basic.10jqka.com.cn/{code}/'
        r = requests.get(url, headers=headers, timeout=8)
        # Look for industry info in the page
        # Pattern: 所属行业
        m = re.search(r'所属行业[：:]\s*<a[^>]*>([^<]+)</a>', r.text)
        if not m:
            m = re.search(r'所属行业[：:]\s*([^<]+)', r.text)
        if m:
            industry = m.group(1).strip()
            s['sector'] = industry
            smap[s['code']] = industry
            print(f'  {s["code"]} {s["name"]} -> {industry}')
        else:
            print(f'  {s["code"]} {s["name"]} -> NOT FOUND on THS')
    except Exception as e:
        print(f'  {s["code"]} {s["name"]} -> ERROR: {type(e).__name__}')
    import time
    time.sleep(1)

# Save
with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'w', encoding='utf-8') as f:
    json.dump(smap, f, ensure_ascii=False, indent=2)

print('\nDone!')

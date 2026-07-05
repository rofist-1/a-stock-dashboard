import json
import requests
import re
import time

with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'r', encoding='utf-8') as f:
    smap = json.load(f)

codes = [s['code'] for s in data['stocks']]

# Try Sina finance stock info API
# http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/...
# Or use the simpler approach: Baidu finance / Sohu finance

# Approach: use xueqiu API via akshare
import akshare as ak

print('Fetching stock individual info from Xueqiu...')
fixed = 0
for s in data['stocks']:
    code = s['code']
    raw_code = code.split('.')[0]
    prefix = code.split('.')[1].lower()
    
    # Skip if already has a reasonable sector
    existing = s.get('sector', '') or ''
    if existing and existing not in ['煤炭行业']:
        continue
    
    try:
        # Try Xueqiu API
        info = ak.stock_individual_info_xq(symbol=raw_code, market=prefix)
        if info is not None:
            # Find industry row
            industry_row = info[info['item'].str.contains('行业', na=False)]
            if not industry_row.empty:
                industry = industry_row['value'].values[0]
                s['sector'] = industry
                smap[code] = industry
                fixed += 1
                print(f'  {code} {s["name"]}: {existing or "-"} -> {industry}')
                time.sleep(0.5)
    except Exception as e:
        print(f'  {code}: error - {e}')
        time.sleep(1)

print(f'\nFixed {fixed} stocks')

# Save updated files
with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'w', encoding='utf-8') as f:
    json.dump(smap, f, ensure_ascii=False, indent=2)

print('Saved!')

# Print final sectors
print('\n=== 最终行业分布 ===')
for s in data['stocks']:
    print(f'{s["code"]:>10} {s["name"]:<6} [{s.get("sector","") or "-"}]')

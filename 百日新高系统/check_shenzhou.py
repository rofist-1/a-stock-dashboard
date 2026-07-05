import json

# Find 神州数码 code from stock_list
with open('C:/Users/Rofis/Desktop/百日新高系统/stock_list.json', 'r', encoding='utf-8') as f:
    stocks = json.load(f)

codes = []
for s in stocks:
    if '神州' in s['name']:
        print(f'stock_list: {s["code"]} -> {s["name"]}')
        codes.append(s['code'])

# Check sector map
with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'r', encoding='utf-8') as f:
    sectors = json.load(f)

for c in codes:
    if c in sectors:
        print(f'sector_map: {c} -> {sectors[c]}')
    else:
        # Try without suffix
        for k, v in sectors.items():
            if c.split('.')[0] in k or k.split('.')[0] in c:
                print(f'sector_map partial: {k} -> {v}')

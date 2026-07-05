import json
with open('C:/Users/Rofis/Desktop/百日新高系统/stock_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for s in data:
    if '肇民' in s['name']:
        print(f'{s["code"]} {s["name"]}')

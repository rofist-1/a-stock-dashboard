import json

path = 'C:/Users/Rofis/Desktop/百日新高系统/sector_map.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

old = data.get('000034', 'N/A')
print(f'Before: 000034 -> {old}')

# 神州数码 is an IT/digital services company, should be in 计算机行业 or similar
# Check what similar IT companies are mapped to
for code, sector in data.items():
    if '计算机' in sector or '软件' in sector or 'IT' in sector:
        print(f'  Reference: {code} -> {sector}')
        break

data['000034'] = '计算机行业'

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print('Fixed!')

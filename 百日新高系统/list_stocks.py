import json

with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'共 {len(data["stocks"])} 只股票')
print()
for i, s in enumerate(data['stocks'], 1):
    print(f'{i:>2}. {s["code"]:>10} {s["name"]:<8} [{s["sector"] or "-"}]')

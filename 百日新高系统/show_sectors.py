import json

with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('=== 有行业（19只）===')
for s in data['stocks']:
    sec = (s.get('sector','') or '').strip()
    if sec:
        print(f'  {s["code"]:>10} {s["name"]:<6} [{sec}]')

print(f'\n=== 缺少行业（34只）===')
for s in data['stocks']:
    sec = (s.get('sector','') or '').strip()
    if not sec:
        print(f'  {s["code"]:>10} {s["name"]:<6}')

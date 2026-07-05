import json

with open('C:/Users/Rofis/Desktop/data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'共 {len(data)} 条记录\n')
print('日期       s1板块    总数  新高  s2板块    总数  新高  s3板块    总数  新高  新高  差值  涨停')
print('-' * 100)
for r in data[-40:]:
    d = r['date']
    nd = (r.get('newHigh',0) or 0) - (r.get('newLow',0) or 0)
    s1 = r.get('s1Name','') or ''
    s2 = r.get('s2Name','') or ''
    s3 = r.get('s3Name','') or ''
    print(f'{d} {s1:>6} {r.get("s1Total",0):>5} {r.get("s1New",0):>4}  {s2:>6} {r.get("s2Total",0):>5} {r.get("s2New",0):>4}  {s3:>6} {r.get("s3Total",0):>5} {r.get("s3New",0):>4}  {r.get("newHigh",0):>4} {nd:>5} {r.get("limitUp",0):>4}')

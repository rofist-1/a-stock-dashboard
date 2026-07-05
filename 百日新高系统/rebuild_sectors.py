import json
import akshare as ak
import time

print('Step 1: Getting industry boards from TongHuashun...')
boards_df = ak.stock_board_industry_name_ths()
boards = boards_df['name'].tolist()
print(f'Got {len(boards)} boards')

print('Step 2: Building code->sector map...')
code_to_sector = {}
for i, board in enumerate(boards):
    try:
        cons = ak.stock_board_industry_cons_ths(symbol=board)
        for _, row in cons.iterrows():
            c = str(row.get('代码', ''))
            if c:
                if c.startswith('6'):
                    c = c + '.SH'
                elif c.startswith('0') or c.startswith('3'):
                    c = c + '.SZ'
                elif c.startswith('8'):
                    c = c + '.BJ'
                code_to_sector[c] = board
        if (i+1) % 20 == 0:
            print(f'  {i+1}/{len(boards)} boards processed ({len(code_to_sector)} stocks)')
        time.sleep(0.3)
    except Exception as e:
        print(f'  Error on {board}: {e}')

print(f'Total mapped: {len(code_to_sector)} stocks')

# Load current data
with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Update 53 stocks
updated = 0
for s in data['stocks']:
    c = s['code']
    if c in code_to_sector:
        new_sector = code_to_sector[c]
        if s.get('sector') != new_sector:
            print(f'  {c} {s["name"]}: {s.get("sector","-")} -> {new_sector}')
            s['sector'] = new_sector
            updated += 1

print(f'\nUpdated {updated} stocks')

# Also update full sector_map.json
with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'r', encoding='utf-8') as f:
    smap = json.load(f)
smap.update(code_to_sector)
with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'w', encoding='utf-8') as f:
    json.dump(smap, f, ensure_ascii=False, indent=2)

# Save updated surge data
with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('\nFinal sectors for 53 stocks:')
for s in data['stocks']:
    print(f'  {s["code"]:>10} {s["name"]:<6} [{s.get("sector","") or "-"}]')

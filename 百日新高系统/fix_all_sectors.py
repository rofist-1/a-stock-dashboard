import json
import akshare as ak

with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get all stock codes
codes = [s['code'] for s in data['stocks']]

# Try to get industry classification from akshare
# Use stock_board_industry_cons_em to get all stocks per industry
print('Fetching industry board data from EastMoney...')
try:
    df = ak.stock_board_industry_name_em()
    boards = df['板块名称'].tolist()
    print(f'Got {len(boards)} industry boards')

    # Build code->sector map from all boards
    code_to_sector = {}
    for board in boards:
        try:
            cons = ak.stock_board_industry_cons_em(symbol=board)
            for _, row in cons.iterrows():
                c = row.get('代码', '')
                if c:
                    # Normalize code
                    if c.startswith('6'):
                        c = c + '.SH'
                    else:
                        c = c + '.SZ'
                    code_to_sector[c] = board
        except:
            pass

    # Update stocks
    updated = 0
    for s in data['stocks']:
        c = s['code']
        if c in code_to_sector:
            if s.get('sector') != code_to_sector[c]:
                s['sector'] = code_to_sector[c]
                updated += 1

    print(f'Updated {updated}/{len(data["stocks"])} stocks')

    # Also update sector_map.json
    with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'r', encoding='utf-8') as f:
        smap = json.load(f)
    smap.update(code_to_sector)
    with open('C:/Users/Rofis/Desktop/百日新高系统/sector_map.json', 'w', encoding='utf-8') as f:
        json.dump(smap, f, ensure_ascii=False, indent=2)
    print(f'Updated sector_map.json with {len(code_to_sector)} entries')

    # Save updated file
    with open('C:/Users/Rofis/Desktop/百日新高系统/底部放量_20260617.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('Saved updated 底部放量_20260617.json')

    # Print results
    print('\n=== 修正后行业分布 ===')
    for s in data['stocks']:
        print(f'  {s["code"]:>10} {s["name"]:<8} [{s["sector"] or "-"}]')

except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

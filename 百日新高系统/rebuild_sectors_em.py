import json
import requests
import time

def get_em_boards():
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': 1, 'pz': 500, 'po': 1, 'np': 1,
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:90+t:2+f:!50',
        'fields': 'f12,f14'
    }
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    data = r.json()
    return [(item['f12'], item['f14']) for item in data['data']['diff']]

def get_board_stocks(board_code, board_name):
    url = 'https://push2.eastmoney.com/api/qt/clist/get'
    params = {
        'pn': 1, 'pz': 500, 'po': 0, 'np': 1,
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': f'b:{board_code}+f:!50',
        'fields': 'f12,f14'
    }
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    data = r.json()
    stocks = []
    for item in data['data']['diff']:
        code = str(item['f12'])
        if code.startswith('6'):
            code = code + '.SH'
        elif code.startswith('0') or code.startswith('3'):
            code = code + '.SZ'
        stocks.append(code)
    return stocks

print('Getting all industry boards from EastMoney...')
boards = get_em_boards()
print(f'Got {len(boards)} boards')

# Build code->sector map
code_to_sector = {}
board_codes_processed = 0
for bk_code, bk_name in boards:
    try:
        stocks = get_board_stocks(bk_code, bk_name)
        for c in stocks:
            code_to_sector[c] = bk_name
        board_codes_processed += 1
        if board_codes_processed % 50 == 0:
            print(f'  {board_codes_processed}/{len(boards)} boards ({len(code_to_sector)} stocks mapped)')
        time.sleep(0.2)
    except Exception as e:
        print(f'  Error on {bk_name}: {e}')

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
        old = s.get('sector', '') or ''
        # Only update if it was missing or was wrong
        if not old or old == '煤炭行业':
            if old != new_sector:
                print(f'  {c} {s["name"]}: [{old}] -> [{new_sector}]')
                s['sector'] = new_sector
                updated += 1
    else:
        if not (s.get('sector', '') or ''):
            print(f'  {c} {s["name"]}: still MISSING')

print(f'\nUpdated {updated} stocks')

# Update sector_map.json
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
    sec = s.get('sector', '') or '-'
    print(f'  {s["code"]:>10} {s["name"]:<6} [{sec}]')

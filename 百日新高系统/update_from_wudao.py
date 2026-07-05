# -*- coding: utf-8 -*-
"""用悟道API更新底部放量JSON（替换akshare，解决东方财富源不通）"""
import json, os, sys
from wudao_client import get_kline

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_FILE = os.path.join(DATA_DIR, '底部放量_20260623.json')
NEW_FILE = os.path.join(DATA_DIR, '底部放量_20260624.json')

def calc_ema(vals, n):
    k = 2 / (n + 1)
    e = sum(vals[-n:]) / n
    for v in vals[-(n-1):]:
        e = v * k + e * (1 - k)
    return e

def calc_atr(rows, n=14):
    trs = []
    for i in range(1, len(rows)):
        h = rows[i]['high']
        l = rows[i]['low']
        pc = rows[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return sum(trs) / len(trs) if trs else 0
    return sum(trs[-n:]) / n

def dir_str(val, prev_val, thr=0.5):
    if prev_val is None or prev_val == 0:
        return '--'
    chg = (val - prev_val) / prev_val * 100
    return '上升' if chg > thr else ('下降' if chg < -thr else '走平')

def update_stock(s):
    code_raw = s['code'].replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
    rows = get_kline(code_raw, 65)
    if len(rows) < 20:
        print(f'  {s["code"]}: 数据不足({len(rows)}行), 跳过')
        return

    closes = [r['close'] for r in rows]
    today = rows[-1]
    yesterday = rows[-2] if len(rows) >= 2 else rows[-1]

    s['close'] = round(today['close'], 2)
    s['change'] = round(today['pct_chg'], 2)
    s['amount_yi'] = round(today['amount'] / 1e8, 1)
    s['date'] = today['date'][:4] + '-' + today['date'][4:6] + '-' + today['date'][6:8]
    s['trade_day'] = s['date']

    # MA / EMA / ATR
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    ma13 = sum(closes[-13:]) / 13
    ma5 = sum(closes[-5:]) / 5
    ema5 = calc_ema(closes, 5)
    ema13 = calc_ema(closes, 13)
    atr14 = calc_atr(rows, 14)

    s['ma60'] = round(ma60, 2) if ma60 else None
    s['ma13'] = round(ma13, 2)
    s['ma5'] = round(ma5, 2)
    s['ema5'] = round(ema5, 2)
    s['ema13'] = round(ema13, 2)
    s['atr14'] = round(atr14, 2) if atr14 else None

    # pct from MAs
    c = s['close']
    s['pct_from_ma60'] = round((c - s['ma60']) / s['ma60'] * 100, 1) if s['ma60'] else None
    s['pct_from_ma13'] = round((c - s['ma13']) / s['ma13'] * 100, 1)
    s['pct_from_ma5'] = round((c - s['ma5']) / s['ma5'] * 100, 1)
    s['pct_from_ema5'] = round((c - s['ema5']) / s['ema5'] * 100, 1)
    s['pct_from_ema13'] = round((c - s['ema13']) / s['ema13'] * 100, 1)

    # directions
    def ema_n(vals, n):
        k = 2/(n+1); e = sum(vals[-n:])/n
        for v in vals[-(n-1):]: e = v*k + e*(1-k)
        return e

    s['ma60_dir'] = dir_str(s['ma60'], sum(closes[-120:-60])/60 if len(closes) >= 120 else None) if s['ma60'] else '--'
    s['ma13_dir'] = dir_str(ma13, sum(closes[-23:-10])/13 if len(closes) >= 23 else None)
    s['ma5_dir'] = dir_str(ma5, sum(closes[-10:-5])/5 if len(closes) >= 10 else None)
    s['ema5_dir'] = dir_str(ema5, ema_n(closes[:-1], 5) if len(closes) > 5 else None, 0.3)
    s['ema13_dir'] = dir_str(ema13, ema_n(closes[:-1], 13) if len(closes) > 13 else None, 0.3)

    # low_60 from available data
    if len(rows) >= 60:
        s['low_60'] = min(r['low'] for r in rows[-60:])
        s['surge_from_low'] = round((c - s['low_60']) / s['low_60'] * 100, 1)

    # vol ratio vs 60-day avg
    amounts = [r['amount'] for r in rows[-61:-1]]
    if amounts:
        avg_vol = sum(amounts) / len(amounts)
        s['vol_ratio_vs_60'] = round(today['amount'] / avg_vol, 1) if avg_vol > 0 else None

    print(f'  {s["code"]}: c={s["close"]} chg={s["change"]}% ma60={s["ma60"]} ema13={s["ema13"]} atr={s["atr14"]}')

def main():
    with open(OLD_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    data['trade_day'] = '2026-06-24'
    data['select_date'] = '2026-06-24'
    data['market_info']['trade_day'] = '2026-06-24'

    print('更新个股数据...')
    for s in data['stocks']:
        update_stock(s)

    # also update hot_resonance_stocks
    for s in data.get('hot_resonance_stocks', []):
        update_stock(s)

    with open(NEW_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n已输出: {NEW_FILE}')

if __name__ == '__main__':
    main()

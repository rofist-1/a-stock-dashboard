# -*- coding: utf-8 -*-
"""通达信盘后数据扫描 v1.0"""
import os, struct, json
from collections import defaultdict
import numpy as np

TDX_DIR = r'C:\new_tdx\vipdoc'
BASE = r'C:\Users\Rofis\Desktop'
CONCEPT_CACHE = os.path.join(BASE, '百日新高系统', 'concept_stocks_cache.json')
RPS_CACHE = os.path.join(BASE, '百日新高系统', 'concept_rps_cache.json')

def read_day_file(filepath):
    """读取通达信.day文件，返回DataFrame"""
    records = []
    with open(filepath, 'rb') as f:
        while True:
            buf = f.read(32)
            if len(buf) < 32: break
            date, op, hi, lo, cl, amt, vol, _ = struct.unpack('I I I I I f I I', buf)
            if date < 20240101: continue
            records.append([date, op/100.0, hi/100.0, lo/100.0, cl/100.0, amt, vol])
    return records

def get_latest_date():
    """扫描一个文件确定最新日期"""
    import random
    for pfx in ['sh', 'sz']:
        d = os.path.join(TDX_DIR, pfx, 'lday')
        if os.path.exists(d):
            files = os.listdir(d)
            if files:
                f = os.path.join(d, files[0])
                recs = read_day_file(f)
                if recs: return recs[-1][0]
    return None

def load_concept_map():
    cmap = defaultdict(list)
    if os.path.exists(CONCEPT_CACHE):
        with open(CONCEPT_CACHE, encoding='utf-8') as f:
            data = json.load(f)
        for concept, codes in data.items():
            for c in codes:
                cc = c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:]
                cmap[cc].append(concept)
    return cmap

def load_rps():
    if os.path.exists(RPS_CACHE):
        with open(RPS_CACHE, encoding='utf-8') as f:
            return json.load(f)
    return {}

# ========= 主扫描 =========
print("=" * 70)
print("  通达信盘后数据 · 每日扫描")
print("=" * 70)

# 1. 确定最新日期
latest = get_latest_date()
print(f"\n最新日期: {latest} ({str(latest)[:4]}-{str(latest)[4:6]}-{str(latest)[6:8]})")

# 2. 加载概念映射
concept_map = load_concept_map()
print(f"概念映射: {len(concept_map)}只股票")

# 3. 逐市场扫描
concept_stats = defaultdict(lambda: {'limit_up': 0, 'new_high': 0, 'stocks': []})
all_stocks = []

for market in ['sh', 'sz', 'bj']:
    lday_dir = os.path.join(TDX_DIR, market, 'lday')
    if not os.path.exists(lday_dir): continue
    files = os.listdir(lday_dir)
    print(f"\n  {market}: {len(files)} files...")

    for fn in files:
        if not fn.endswith('.day'): continue
        raw_code = fn.replace('.day', '')
        # 去掉市场前缀: sh600000 → 600000
        if raw_code.startswith('sh') or raw_code.startswith('sz') or raw_code.startswith('bj'):
            code = raw_code[2:]
        else:
            code = raw_code
        full_code = raw_code

        records = read_day_file(os.path.join(lday_dir, fn))
        if len(records) < 60: continue

        # 取最近两天数据
        today = records[-1]
        yesterday = records[-2]
        date_t, open_t, high_t, low_t, close_t, amt_t, vol_t = today
        close_y = yesterday[4]

        if close_y == 0: continue
        chg_pct = (close_t - close_y) / close_y * 100

        # 涨停判断 (10% 或 20%)
        limit_up_pct = 19.5 if code.startswith('3') or code.startswith('688') or code.startswith('4') or code.startswith('8') else 9.5
        is_limit_up = chg_pct >= limit_up_pct

        # MA60
        closes = [r[4] for r in records[-60:]]
        ma60 = sum(closes) / len(closes)
        above_ma60 = close_t > ma60

        # 量比
        vols = [r[6] for r in records[-6:]]
        avg_vol5 = sum(vols[:5]) / 5 if vols[5] > 0 else 1
        vol_ratio = vols[5] / avg_vol5 if avg_vol5 > 0 else 0

        # 百日新高/新低
        closes100 = [r[4] for r in records[-100:]]
        is_100d_high = close_t >= max(closes100)
        is_100d_low = close_t <= min(closes100)

        # 振幅
        amplitude = (high_t - low_t) / close_y * 100

        # 概念归属
        concepts = concept_map.get(code, [])

        stock_info = {
            'code': code, 'market': market, 'full_code': full_code,
            'close': close_t, 'chg': round(chg_pct, 2),
            'limit_up': is_limit_up,
            'ma60': round(ma60, 2), 'above_ma60': above_ma60,
            'vol_ratio': round(vol_ratio, 2),
            'amount': amt_t, 'volume': vol_t,
            'new_high': is_100d_high, 'new_low': is_100d_low,
            'amplitude': round(amplitude, 2),
            'concepts': concepts,
        }
        all_stocks.append(stock_info)

        # 按概念统计
        for cpt in concepts:
            if is_limit_up:
                concept_stats[cpt]['limit_up'] += 1
            if is_100d_high:
                concept_stats[cpt]['new_high'] += 1
            concept_stats[cpt]['stocks'].append(stock_info)

# ========= 输出 =========
total_limit_up = sum(1 for s in all_stocks if s['limit_up'])
total_new_high = sum(1 for s in all_stocks if s['new_high'])
total_new_low = sum(1 for s in all_stocks if s['new_low'])
total_up = sum(1 for s in all_stocks if s['chg'] > 0)
total_down = sum(1 for s in all_stocks if s['chg'] < 0)
total_above_ma60 = sum(1 for s in all_stocks if s['above_ma60'])

print(f"\n{'='*70}")
print(f"  全市场扫描结果 ({str(latest)[:4]}-{str(latest)[4:6]}-{str(latest)[6:8]})")
print(f"{'='*70}")
print(f"  股票总数: {len(all_stocks)}")
print(f"  上涨: {total_up}  下跌: {total_down}")
print(f"  涨停: {total_limit_up}")
print(f"  百日新高: {total_new_high}  百日新低: {total_new_low}")
print(f"  差值: {total_new_high - total_new_low}")
print(f"  站上MA60: {total_above_ma60}")

# 概念统计
print(f"\n====== 核心概念板块统计 ======")
print(f"  {'概念':<14} {'涨停':>5} {'百日新高':>7} {'RPS10':>6} {'RPS20':>6} {'RPS60':>6} {'状态':>8}")
print(f"  {'-'*57}")

rps_data = load_rps().get('rps', {})

for cpt_name in sorted(concept_stats.keys()):
    cs = concept_stats[cpt_name]
    lu = cs['limit_up']
    nh = cs['new_high']
    r = rps_data.get(cpt_name, {})
    r10 = r.get('10', 0); r20 = r.get('20', 0); r60 = r.get('60', 0)

    # 四态标记
    all85 = (r10 >= 85 and r20 >= 85 and r60 >= 85)
    two85 = sum(1 for v in [r10, r20, r60] if v >= 85) >= 2
    if all85: tag = '[HIDDEN]' if lu < 5 else '[RESONANT]'
    elif two85: tag = '[NEAR]'
    elif lu >= 10: tag = '[BURST]'
    else: tag = ''

    print(f'  {cpt_name:<14} {lu:>5} {nh:>7} {r10:>6} {r20:>6} {r60:>6} {tag:>8}')

# A1候选: 量比>=1.5, 涨幅5-20%, 站上MA60, 属于核心概念
print(f"\n====== A1突破候选 (量比>=1.5, 涨幅5-20%, 站上MA60) ======")
a1_candidates = [s for s in all_stocks 
    if s['vol_ratio'] >= 1.5 and 5 <= s['chg'] <= 20 
    and s['above_ma60'] and s['concepts']]
a1_candidates.sort(key=lambda x: x['vol_ratio'], reverse=True)

for s in a1_candidates[:15]:
    cpts = ','.join(s['concepts'][:2])
    print(f"  {s['full_code']:<12} {s['chg']:>+6.1f}% vol={s['vol_ratio']:.1f} amp={s['amplitude']:.1f}% MA60dist={(s['close']-s['ma60'])/s['ma60']*100:+.0f}% {cpts}")

# A2候选
print(f"\n====== [HIDDEN] CPO概念股票 ======")
for s in all_stocks:
    if 'CPO' in s.get('concepts', []):
        above_ma20 = '(待验)'
        print(f"  {s['full_code']:<12} close={s['close']:.1f} chg={s['chg']:+.1f}% vol={s['vol_ratio']:.1f} Ma60={s['ma60']:.1f}")

# 分歧日候选 (振幅>=4%, 量比>=1.5, 涨幅>=5%)
print(f"\n====== P1分歧候选 (振幅>=4%, 量比>=1.5, 涨>=5%) ======")
div_candidates = [s for s in all_stocks
    if s['amplitude'] >= 4 and s['vol_ratio'] >= 1.5
    and s['chg'] >= 5 and s['concepts']]
div_candidates.sort(key=lambda x: x['vol_ratio'], reverse=True)
for s in div_candidates[:10]:
    cpts = ','.join(s['concepts'][:2])
    print(f"  {s['full_code']:<12} chg={s['chg']:>+6.1f}% amp={s['amplitude']:>5.1f}% vol={s['vol_ratio']:.2f} {cpts}")

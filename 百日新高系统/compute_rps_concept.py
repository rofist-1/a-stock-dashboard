# -*- coding: utf-8 -*-
"""
概念RPS v3 — 从悟道MCP缓存 → 计算概念RPS
"""
import pickle, glob, os, json
import numpy as np
import pandas as pd
from collections import defaultdict

BASE = r'C:\Users\Rofis\Desktop'
cache_dir = os.path.join(BASE, '百日新高系统', 'kline_cache')
concept_fp = os.path.join(BASE, '百日新高系统', 'concept_stocks_cache.json')
sm = json.load(open(os.path.join(BASE, '百日新高系统', 'sector_map.json'), encoding='utf-8'))

# 从本地缓存加载概念股
if not os.path.exists(concept_fp):
    print('概念缓存不存在，请先运行概念数据采集')
    exit()

with open(concept_fp, encoding='utf-8') as f:
    concept_cache = json.load(f)

print('=' * 65)
print('  概念 RPS 计算')
print('=' * 65)

# 加载个股
all_files = glob.glob(os.path.join(cache_dir, '*.pkl'))
universe = {}
for f in all_files:
    try:
        with open(f, 'rb') as fh: data = pickle.load(fh)
        df = data.get('df', data) if isinstance(data, dict) else data
        if not hasattr(df, 'iloc') or len(df) < 120: continue
        cols_l = {c.lower(): c for c in df.columns}
        dc = cols_l.get('date', None)
        if dc is None: continue
        df['date'] = pd.to_datetime(df[dc]); df = df.set_index('date').sort_index()
        for cn in df.columns:
            if cn.lower() == 'close': df['close'] = pd.to_numeric(df[cn], errors='coerce'); break
        if 'close' not in df.columns: continue
        code = os.path.basename(f).replace('.pkl', '')
        clean = code.replace('sh','').replace('sz','').replace('bj','')
        sec = sm.get(code, sm.get(clean, ''))
        if df.index[-1] < pd.Timestamp('2026-06-01'): continue
        universe[code] = {'df': df, 'sector': sec}
    except: pass

latest = max(i['df'].index[-1] for i in universe.values())
print(f'个股: {len(universe)}只  日期: {latest.strftime("%Y-%m-%d")}')

# Build concept→code mapping (6-digit codes)
code_to_concept = defaultdict(list)
concept_counts = {}
for cpt_name, codes in concept_cache.items():
    valid = 0
    for cc in codes:
        c6 = cc.replace('sh','').replace('sz','').replace('bj','')[-6:]
        code_to_concept[c6].append(cpt_name)
        valid += 1
    concept_counts[cpt_name] = valid

print(f'概念数: {len(concept_counts)}个')

# Compute concept returns
cpt_rets = defaultdict(lambda: defaultdict(list))
for code, info in universe.items():
    clean = code.replace('sh','').replace('sz','').replace('bj','')[-6:]
    concepts = code_to_concept.get(clean, [])
    if not concepts: continue
    df = info['df']
    if latest not in df.index: continue
    idx = df.index.get_loc(latest)
    c = df['close']
    for w in [10, 20, 60]:
        if idx >= w:
            ret = (c.iloc[idx] - c.iloc[idx - w]) / c.iloc[idx - w] * 100
            for cpt in concepts: cpt_rets[cpt][w].append(ret)

# RPS rank
rps = {}
for w in [10, 20, 60]:
    avgs = {}
    for cpt, wr in cpt_rets.items():
        if w in wr and len(wr[w]) >= 3:
            avgs[cpt] = np.mean(wr[w])
    if len(avgs) < 3: continue
    names = list(avgs.keys()); vals = list(avgs.values())
    ranks = np.argsort(np.argsort(vals))
    for i, n in enumerate(names):
        if n not in rps: rps[n] = {}
        rps[n][w] = ranks[i] / max(len(ranks) - 1, 1) * 100

# === OUTPUT ===
print(f'\n{"="*65}')
print(f'  概念RPS (>=85) — {latest.strftime("%Y-%m-%d")}')
print(f'{"="*65}')
print(f'{"概念":<14} {"RPS10":>6} {"RPS20":>6} {"RPS60":>6} {"成分":>5}')
print('-' * 42)
core = []
for cpt in sorted(rps.keys(), key=lambda x: sum(rps[x].values()), reverse=True):
    r = rps[cpt]; ok = all(r.get(w, 0) >= 85 for w in [10, 20, 60])
    cnt = concept_counts.get(cpt, 0)
    mk = ' ★' if ok else ''
    if ok: core.append(cpt)
    print(f'{cpt:<14} {r.get(10,0):>6.0f} {r.get(20,0):>6.0f} {r.get(60,0):>6.0f} {cnt:>5}{mk}')
print(f'\n核心概念战场: {", ".join(core) if core else "无"}')

# === 申万行业RPS (同样逻辑，对标) ===
sec_rets = defaultdict(list)
for code, info in universe.items():
    sec = info.get('sector', '')
    if not sec or latest not in info['df'].index: continue
    idx = info['df'].index.get_loc(latest)
    c = info['df']['close']
    for w in [10, 20, 60]:
        if idx >= w:
            ret = (c.iloc[idx] - c.iloc[idx - w]) / c.iloc[idx - w] * 100
            sec_rets[(sec, w)].append(ret)

sec_avgs = {}
for (s, w), rets in sec_rets.items():
    if len(rets) >= 3: sec_avgs[(s, w)] = np.mean(rets)

sec_rps = {}
for w in [10, 20, 60]:
    pairs = [(s, v) for (ss, ww), v in sec_avgs.items() if ww == w]
    if len(pairs) < 3: continue
    vals = [v for _, v in pairs]; ranks = np.argsort(np.argsort(vals))
    for i, (s, _) in enumerate(pairs):
        if s not in sec_rps: sec_rps[s] = {}
        sec_rps[s][w] = ranks[i] / max(len(ranks) - 1, 1) * 100

core_ind = []
print(f'\n{"="*65}')
print(f'  申万行业RPS (>=85)')
print(f'{"="*65}')
for s in sorted(sec_rps.keys(), key=lambda x: sum(sec_rps[x].values()), reverse=True):
    r = sec_rps[s]; ok = all(r.get(w, 0) >= 85 for w in [10, 20, 60])
    mk = ' ★' if ok else ''
    if ok: core_ind.append(s)
    print(f'{s:<14} {r.get(10,0):>6.0f} {r.get(20,0):>6.0f} {r.get(60,0):>6.0f}{mk}')

print(f'\n{"="*65}')
print(f'  双轨对比')
print(f'{"="*65}')
print(f'  概念主线: {", ".join(core) if core else "无"}')
print(f'  行业主线: {", ".join(core_ind) if core_ind else "无"}')
overlap = set(core) & set(core_ind)
print(f'  重叠: {", ".join(overlap) if overlap else "无"}')

"""concept_rps_updater v2 — 从通达信.day读取，每日更新"""
import os,struct,json
from collections import defaultdict
import numpy as np

TDX = r'C:\new_tdx\vipdoc'
BASE = r'C:\Users\Rofis\Desktop'
CACHE = os.path.join(BASE, '百日新高系统', 'concept_stocks_cache.json')
OUT = os.path.join(BASE, '百日新高系统', 'concept_rps_cache.json')

cmap = defaultdict(list)
if os.path.exists(CACHE):
    with open(CACHE, encoding='utf-8') as f:
        for cpt, codes in json.load(f).items():
            for c in codes:
                cc = c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:]
                cmap[cc].append(cpt)

date = 20260708
concept_rets = defaultdict(lambda: defaultdict(list))

for mkt in ['sh','sz','bj']:
    d = os.path.join(TDX, mkt, 'lday')
    if not os.path.exists(d): continue
    for fn in os.listdir(d):
        if not fn.endswith('.day'): continue
        code = fn.replace('.day','')[2:]
        concepts = cmap.get(code, [])
        if not concepts: continue

        with open(os.path.join(d, fn), 'rb') as f:
            closes = []
            while True:
                buf = f.read(32)
                if len(buf) < 32: break
                dt, _, _, _, cl = struct.unpack_from('I I I I I', buf)
                if dt <= date: closes.append((dt, cl/100.))

        if len(closes) < 60: continue
        close_today = closes[-1][1]
        for w in [10, 20, 60]:
            if len(closes) > w:
                past = closes[-w-1][1] if len(closes) > w else closes[0][1]
                if past > 0:
                    ret = (close_today - past) / past * 100
                    for cpt in concepts: concept_rets[cpt][w].append(ret)

# RPS rank
rps = {}
for w in [10,20,60]:
    avgs = {}
    for cpt, windows in concept_rets.items():
        wr = windows.get(w, [])
        if len(wr) >= 3:
            avgs[cpt] = np.mean(wr)
    if len(avgs) < 3: continue
    names = list(avgs.keys()); vals = list(avgs.values())
    ranks = np.argsort(np.argsort(vals))
    for i, n in enumerate(names):
        if n not in rps: rps[n] = {}
        rps[n][w] = ranks[i] / max(len(ranks)-1, 1) * 100

# Print
fmt = '{:<14} {:>6} {:>6} {:>6} {:>8}'
print(f'Date: {date}')
print(fmt.format('Concept', 'RPS10', 'RPS20', 'RPS60', 'Status'))
print('-'*42)
for cpt in sorted(rps, key=lambda x: sum(rps[x].values()), reverse=True):
    r = rps[cpt]; ok = all(r.get(w,0)>=85 for w in [10,20,60])
    tag = 'HIDDEN' if ok else ''
    print(fmt.format(cpt, str(int(r.get(10,0))), str(int(r.get(20,0))), str(int(r.get(60,0))), tag))

# Save
json.dump({
    'date': str(date), 'rps': {k:{str(w):int(v) for w,v in rps[k].items()} for k in rps},
    'core': [c for c in rps if all(rps[c].get(w,0)>=85 for w in [10,20,60])]
}, open(OUT,'w',encoding='utf-8'), ensure_ascii=False)
print(f'Saved: {OUT}')

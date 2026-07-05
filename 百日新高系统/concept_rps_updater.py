# -*- coding: utf-8 -*-
"""
concept_rps_updater.py v1.0
============================
每日盘后自动更新14个核心概念的RPS(10/20/60)
基于本地kline_cache + 悟道API概念成分股映射
"""
import pickle, glob, os, json, time
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

BASE = r'C:\Users\Rofis\Desktop'
SYS_DIR = os.path.join(BASE, '百日新高系统')
CACHE_DIR = os.path.join(SYS_DIR, 'kline_cache')
CONCEPT_CACHE = os.path.join(SYS_DIR, 'concept_stocks_cache.json')
RPS_OUTPUT = os.path.join(SYS_DIR, 'concept_rps_cache.json')

# 核心概念 tsCode（悟道API）
CORE_CONCEPTS = {
    '机器人概念': 'cls80201',
    '汽车零部件': 'cls80266',
    '商业航天': 'cls82517',
    '半导体芯片': 'cls80195',
    '半导体设备': 'cls80456',
    '功率半导体': 'cls80537',
    '液冷IDC': 'cls81978',
    '创新药': 'cls80044',
    'CRO/CMO': 'cls80481',
    'CPO': 'cls81935',
    '减速器': 'cls80602',
    '算力工程': 'cls80550',
    '人形机器人': 'cls82064',
    '芯片产业链': 'cls80457',
}

def fetch_concept_stocks_api():
    """通过悟道REST API获取全量概念成分股（补充缓存）"""
    key_file = os.path.join(SYS_DIR, '.wudao_api_key')
    api_key = ''
    if os.path.exists(key_file):
        with open(key_file) as f: api_key = f.read().strip()
    if not api_key: return {}
    
    import requests
    headers = {'Authorization': f'Bearer {api_key}'}
    base = 'https://stock.quicktiny.cn/api/openclaw'
    
    all_concepts = {}
    for name, tscode in CORE_CONCEPTS.items():
        codes = set()
        for page in range(1, 6):  # 最多5页, 每页20只
            try:
                r = requests.get(f'{base}/concept-stocks', headers=headers,
                    params={'tsCode': tscode, 'page': page, 'limit': 20}, timeout=10)
                if r.status_code == 200:
                    data = r.json().get('data', {})
                    items = data.get('rows', data.get('items', []))
                    if not items: break
                    for s in items:
                        c = s.get('code', s.get('tsCode', ''))
                        c = c.replace('.SH','').replace('.SZ','').replace('.BJ','')
                        c = c.replace('sh','').replace('sz','').replace('bj','')
                        codes.add(c[-6:])
                else: break
            except: break
            time.sleep(0.1)
        if codes:
            all_concepts[name] = list(codes)
            print(f'  {name}: {len(codes)}只')
    return all_concepts

def update_concept_cache():
    """从本地缓存加载概念成分股映射"""
    if os.path.exists(CONCEPT_CACHE):
        with open(CONCEPT_CACHE, encoding='utf-8') as f:
            existing = json.load(f)
    else:
        existing = {}
    
    counts = {k: len(v) for k, v in existing.items()}
    return existing, counts

def load_kline_universe():
    """加载kline_cache中所有>120行的个股"""
    files = glob.glob(os.path.join(CACHE_DIR, '*.pkl'))
    universe = {}
    for f in files:
        try:
            with open(f, 'rb') as fh:
                data = pickle.load(fh)
            df = data.get('df', data) if isinstance(data, dict) else data
            if not hasattr(df, 'iloc') or len(df) < 120: continue
            cols_l = {c.lower(): c for c in df.columns}
            dc = cols_l.get('date', None)
            if dc is None: continue
            df['date'] = pd.to_datetime(df[dc])
            df = df.set_index('date').sort_index()
            for cn in df.columns:
                if cn.lower() == 'close': df['close'] = pd.to_numeric(df[cn], errors='coerce'); break
            if 'close' not in df.columns: continue
            code = os.path.basename(f).replace('.pkl', '')
            clean = code.replace('sh','').replace('sz','').replace('bj','')[-6:]
            universe[clean] = df
        except: pass
    return universe

def compute_concept_rps(universe, concept_map, target_date=None):
    """
    计算每个概念的RPS(10/20/60)
    - 概念指数日涨跌 = 成分股等权平均涨跌
    - RPS = 概念区间涨幅在所有概念中的分位×100
    """
    if target_date is None:
        # 使用最新的公共日期
        all_dates = set()
        for df in universe.values():
            all_dates.update(df.index)
        target_date = max(all_dates)
    
    # 构建概念→股票列表(限缓存中有数据的)
    concept_stocks = defaultdict(list)
    for name, codes in concept_map.items():
        for c in codes:
            # 统一转为6位代码
            cc = c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:]
            if cc in universe:
                concept_stocks[name].append(cc)
    
    # 计算每个概念每日等权收益
    concept_daily = {}
    for name, stocks in concept_stocks.items():
        if len(stocks) < 3: continue
        # 收集所有成分股的收盘价序列
        all_ret = []
        for c in stocks:
            df = universe[c]
            # 计算日收益率
            ret = df['close'].pct_change().dropna()
            if len(ret) > 60:
                all_ret.append(ret)
        if len(all_ret) < 3: continue
        # 等权平均
        aligned = pd.concat(all_ret, axis=1).mean(axis=1)
        aligned = aligned.sort_index()
        concept_daily[name] = aligned
    
    # 计算各窗口区间收益
    concept_window_ret = {}
    for name, ret_series in concept_daily.items():
        if target_date not in ret_series.index:
            # 找最近日期
            nearest = max(d for d in ret_series.index if d <= target_date)
        else:
            nearest = target_date
        
        idx = ret_series.index.get_loc(nearest)
        csum = (1 + ret_series).cumprod()
        
        for w in [10, 20, 60]:
            if idx >= w:
                wr = (csum.iloc[idx] / csum.iloc[idx - w] - 1) * 100
                concept_window_ret[(name, w)] = wr
    
    # RPS排名
    rps = {}
    for w in [10, 20, 60]:
        pairs_list = [(n_name2, n_ret) for (n_name2, ww), n_ret in concept_window_ret.items() if ww == w]
        if len(pairs_list) < 3: continue
        vals = [v for n_name2, v in pairs_list]
        ranks = np.argsort(np.argsort(vals))
        for i, (n_name2, _) in enumerate(pairs_list):
            if n_name2 not in rps: rps[n_name2] = {}
            rps[n_name2][w] = ranks[i] / max(len(ranks) - 1, 1) * 100
    
    return rps, concept_window_ret, target_date

def update_rps():
    """主更新函数"""
    dt_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'Concept RPS Updater v1.0 - {dt_str}')
    print('=' * 65)
    
    # 1. 更新概念映射
    print('\n[1/3] 更新概念成分股缓存...')
    concept_map, counts = update_concept_cache()
    total_stocks = sum(len(v) for v in concept_map.values())
    print(f'  概念数: {len(concept_map)}, 总成分股去重: 约{total_stocks}次')
    
    # 2. 加载K线
    print('\n[2/3] 加载K线数据...')
    universe = load_kline_universe()
    print(f'  有效个股: {len(universe)}只')
    
    # 统计概念覆盖率
    for name, codes in concept_map.items():
        in_cache = sum(1 for c in codes if c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:] in universe)
        print(f'    {name}: {in_cache}/{len(codes)}在缓存中')
    
    # 3. 计算RPS
    print('\n[3/3] 计算概念RPS...')
    rps, win_ret, latest_date = compute_concept_rps(universe, concept_map)
    
    # 输出
    print(f'\n{"="*65}')
    print(f'  概念RPS ({latest_date.strftime("%Y-%m-%d")})')
    print(f'{"="*65}')
    print(f'  {"概念":<14} {"RPS10":>6} {"RPS20":>6} {"RPS60":>6} {"成分股":>6} {"RPS>=85":>8}')
    print(f'  {"-"*50}')
    
    core85 = []
    for name in sorted(rps.keys(), key=lambda x: sum(rps[x].values()), reverse=True):
        r = rps[name]; ok = all(r.get(w, 0) >= 85 for w in [10, 20, 60])
        cnt = len(concept_map.get(name, []))
        in_cache = sum(1 for c in concept_map.get(name, []) if c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:] in universe)
        mk = ' ★核心' if ok else ''
        if ok: core85.append(name)
        print(f'  {name:<14} {r.get(10,0):>6.0f} {r.get(20,0):>6.0f} {r.get(60,0):>6.0f} {in_cache:>4}/{cnt:<2} {mk:>8}')
    
    # 保存缓存
    output = {
        'date': latest_date.strftime('%Y-%m-%d'),
        'updated': datetime.now().isoformat(),
        'core_concepts': core85,
        'rps': {k: {str(w): int(v) for w, v in rps[k].items()} for k in rps},
        'concept_stock_count': {k: len(v) for k, v in concept_map.items() if k in rps},
        'concept_cache_count': {k: sum(1 for c in concept_map.get(k,[]) if c.replace('sh','').replace('sz','').replace('bj','').upper()[-6:] in universe) for k in rps},
    }
    with open(RPS_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f'\n  核心概念战场(RPS>=85): {", ".join(core85) if core85 else "无"}')
    print(f'  RPS缓存已保存: {RPS_OUTPUT}')
    return rps, core85

# ============================================================
# 直接运行
# ============================================================
if __name__ == '__main__':
    update_rps()

# -*- coding: utf-8 -*-
"""
日线扫描器 v1.0 — 纯条件B策略
================================
逻辑（全部满足才输出）:
  1. 均线粘合: MA60 > EMA13 且 (MA60-EMA13)/MA60 < 3%
  2. 放量突破: 收盘价 > EMA13*1.01 且 成交量 >= 5日均量*1.5
  3. 板块热度: 所属行业当日涨幅排名 <= 6 (全市场约31个行业前6)

运行:
  python daily_scanner.py                    # 扫描最新交易日
  python daily_scanner.py --date 20260624    # 扫描指定日期
  python daily_scanner.py --list-industries   # 列出所有行业
"""

import sys, os, json, pickle, glob
from datetime import datetime, timedelta
from collections import defaultdict
from statistics import mean
import pandas as pd

_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_script_dir).startswith('百日新高'):
    DATA_DIR = _script_dir
else:
    DATA_DIR = os.path.join(_script_dir, '百日新高系统')
    if not os.path.isdir(DATA_DIR):
        DATA_DIR = _script_dir

# ─── 工具函数 ───────────────────────────────────────────────

def calc_ema(vals, n):
    if len(vals) < n: return None
    k = 2 / (n + 1)
    e = sum(vals[-n:]) / n
    for v in vals[-(n-1):]:
        e = v * k + e * (1 - k)
    return e

def calc_sma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def safe_div(a, b):
    return a / b if b else 0

# ─── 数据加载 ───────────────────────────────────────────────

def load_sector_map():
    fpath = os.path.join(DATA_DIR, 'sector_map.json')
    if not os.path.isfile(fpath):
        print('[!] sector_map.json 未找到')
        return {}
    return json.load(open(fpath, encoding='utf-8'))

def load_kline_cache():
    cache = {}
    cache_dir = os.path.join(DATA_DIR, 'kline_cache')
    if not os.path.isdir(cache_dir):
        return cache
    for fpath in glob.glob(os.path.join(cache_dir, '*.pkl')):
        try:
            fname = os.path.splitext(os.path.basename(fpath))[0]
            raw = pickle.load(open(fpath, 'rb'))
            if not isinstance(raw, dict) or 'df' not in raw:
                continue
            df = raw['df']
            if not isinstance(df, pd.DataFrame) or len(df) < 20:
                continue
            rows = []
            for _, r in df.iterrows():
                d = r.get('date', '')
                d_str = str(d)[:10].replace('-', '') if d == d else ''
                rows.append({
                    'date': d_str,
                    'close': float(r.get('close', 0)),
                    'high': float(r.get('high', 0)),
                    'low': float(r.get('low', 0)),
                    'open': float(r.get('open', 0)),
                    'volume': float(r.get('volume', 0)),
                    'amount': float(r.get('amount', 0)),
                })
            code6 = fname[2:] if len(fname) > 2 and fname[:2] in ('sh','sz') else fname
            if code6.isdigit() and len(code6) == 6:
                cache[code6] = rows
        except:
            pass
    return cache

# ─── 核心扫描 ───────────────────────────────────────────────

def find_latest_trade_date(cache):
    """从所有股票K线中找最新的共同交易日"""
    latest = ''
    for klines in cache.values():
        if klines and klines[-1]['date'] > latest:
            latest = klines[-1]['date']
    return latest

def compute_industry_ranking(cache, sector_map, date_str):
    """
    计算指定日期全行业的平均涨幅排名。
    返回 dict[code] = {industry, industry_rank}
    """
    ind_stocks = defaultdict(list)
    for code, klines in cache.items():
        industry = sector_map.get(code)
        if not industry or len(klines) < 70:
            continue
        idx = next((i for i, k in enumerate(klines) if k['date'] == date_str), None)
        if idx is None or idx < 1:
            continue
        prev_close = klines[idx-1]['close']
        pct = (klines[idx]['close'] - prev_close) / prev_close * 100 if prev_close > 0 else 0
        ind_stocks[industry].append({'code': code, 'pct': pct})

    # 计算各行业平均涨幅
    ind_perf = {}
    for ind, stocks in ind_stocks.items():
        if len(stocks) < 3:
            continue
        avg_pct = mean(s['pct'] for s in stocks)
        ind_perf[ind] = {'avg_pct': round(avg_pct, 2), 'count': len(stocks)}

    # 按涨幅排序
    ranked = sorted(ind_perf.items(), key=lambda x: -x[1]['avg_pct'])
    ind_rank = {}
    for rank, (ind_name, _) in enumerate(ranked, 1):
        ind_rank[ind_name] = rank

    return ind_rank, ind_perf

def scan(cache, sector_map, date_str=None):
    """执行日线扫描"""
    if date_str is None:
        date_str = find_latest_trade_date(cache)
        print(f'  自动检测到最新交易日: {date_str}')

    print(f'  计算行业热度排名 ({date_str})...')
    ind_rank, ind_perf = compute_industry_ranking(cache, sector_map, date_str)

    candidates = []
    stats = {'total_stocks': 0, 'cond1_pass': 0, 'cond2_pass': 0, 'cond3_pass': 0, 'all_pass': 0}

    for code, klines in cache.items():
        sector = sector_map.get(code)
        if len(klines) < 70:
            continue
        stats['total_stocks'] += 1

        # 找到数据日期对应的最新行
        idx = next((i for i, k in enumerate(klines) if k['date'] == date_str), None)
        if idx is None or idx < 60:
            continue

        closes = [k['close'] for k in klines[:idx+1]]
        volumes = [k['volume'] for k in klines[:idx+1]]
        row = klines[idx]

        # 计算技术指标
        ma60 = calc_sma(closes, 60)
        ema13 = calc_ema(closes, 13)
        vol_ma5 = calc_sma(volumes, 5)
        if None in (ma60, ema13, vol_ma5) or ma60 <= 0:
            continue

        # 条件1: 均线粘合 (MA60 > EMA13 且间距 < 3%)
        gap_pct = (ma60 - ema13) / ma60 * 100
        if not (ma60 > ema13 and gap_pct < 3):
            continue
        stats['cond1_pass'] += 1

        # 条件2: 放量突破EMA13
        if not (row['close'] > ema13 * 1.01 and row['volume'] >= vol_ma5 * 1.5):
            continue
        stats['cond2_pass'] += 1

        # 条件3: 板块热度排名前6
        if sector:
            rank = ind_rank.get(sector, 99)
        else:
            rank = 99
        if rank > 6:
            continue
        stats['cond3_pass'] += 1

        stats['all_pass'] += 1

        candidates.append({
            'code': code,
            'name': '',
            'sector': sector or '',
            'close': round(row['close'], 2),
            'pct_chg': round((row['close'] - klines[idx-1]['close']) / klines[idx-1]['close'] * 100, 2),
            'amount_yi': round(row.get('amount', 0) / 1e8, 1),
            'volume_ratio': round(row['volume'] / vol_ma5, 2),
            'ma60': round(ma60, 2),
            'ema13': round(ema13, 2),
            'gap_pct': round(gap_pct, 2),
            'industry_rank': rank,
            'date': date_str,
        })

    return candidates, stats, ind_perf

# ─── 输出 ─────────────────────────────────────────────────────

def print_candidates(candidates, stats, ind_perf):
    print(f'\n{"="*80}')
    print(f'  日线扫描结果 — 纯条件B策略')
    print(f'{"="*80}')
    print(f'  检查 {stats["total_stocks"]} 只股票')
    print(f'  条件1通过(均线粘合):   {stats["cond1_pass"]}')
    print(f'  条件2通过(放量突破):   {stats["cond2_pass"]}')
    print(f'  条件3通过(板块前6):    {stats["cond3_pass"]}')
    print(f'  全部通过:             {stats["all_pass"]}')
    print()

    if not candidates:
        print('  [空] 今日无候选')
        return

    # 按行业排名排序
    candidates.sort(key=lambda x: x['industry_rank'])

    print(f'{"代码":>8} {"行业":>12} {"收盘":>8} {"涨幅":>7} {"成交额":>8} {"量比":>6} {"距MA60":>7} {"行业排名":>6}')
    print(f'{ "-"*60}')
    for c in candidates:
        name_str = ''
        print(f'{c["code"]:>8} {c["sector"][:10]:>10} {c["close"]:>8.2f} {c["pct_chg"]:>+6.2f}% {c["amount_yi"]:>7.1f}亿 {c["volume_ratio"]:>5.1f}x {c["gap_pct"]:>+6.2f}% {c["industry_rank"]:>5}/31')

    # 行业排名总览
    print(f'\n{"="*60}')
    print(f'  行业涨幅排名 (Top 10)')
    print(f'{"="*60}')
    sorted_ind = sorted(ind_perf.items(), key=lambda x: -x[1]['avg_pct'])[:10]
    for i, (ind, perf) in enumerate(sorted_ind, 1):
        print(f'  {i:>2}. {ind:<12} {perf["avg_pct"]:>+6.2f}% ({perf["count"]}只)')

# ─── 主入口 ───────────────────────────────────────────────────

def main():
    print(f'\n{"="*60}')
    print(f'  日线扫描器 v1.0 (纯条件B)')
    print(f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')

    if '--list-industries' in sys.argv:
        sector_map = load_sector_map()
        unique_ind = sorted(set(sector_map.values()))
        print(f'\n  共 {len(unique_ind)} 个行业')
        for ind in unique_ind:
            cnt = sum(1 for v in sector_map.values() if v == ind)
            print(f'  {ind}: {cnt}只')
        return

    print(f'\n[1] 加载行业映射...')
    sector_map = load_sector_map()
    print(f'  加载 {len(sector_map)} 只股票行业映射 ({len(set(sector_map.values()))} 个行业)')

    print(f'\n[2] 加载K线缓存...')
    cache = load_kline_cache()
    print(f'  加载 {len(cache)} 只股票')

    date_str = None
    for i, arg in enumerate(sys.argv):
        if arg == '--date' and i + 1 < len(sys.argv):
            date_str = sys.argv[i + 1]

    print(f'\n[3] 执行扫描...')
    candidates, stats, ind_perf = scan(cache, sector_map, date_str)
    print_candidates(candidates, stats, ind_perf)

    # 保存结果
    if candidates:
        out_path = os.path.join(DATA_DIR, f'日线扫描_{date_str or find_latest_trade_date(cache)}.json')
        json.dump({
            'scan_time': datetime.now().strftime('%Y%m%d_%H%M'),
            'date': date_str or find_latest_trade_date(cache),
            'total_checked': stats['total_stocks'],
            'all_pass': stats['all_pass'],
            'candidates': candidates,
        }, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'\n  结果已保存: {out_path}')

if __name__ == '__main__':
    main()

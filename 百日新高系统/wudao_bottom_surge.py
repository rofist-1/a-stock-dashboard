# -*- coding: utf-8 -*-
"""
每日底部放量扫描 - 悟道API版
============================
用法: python wudao_bottom_surge.py [YYYYMMDD]
依赖: wudao_client.py (openclaw HTTP API)

策略: 
  1. stock_screener 1次调用 → 初筛候选(量比>=2涨幅>=5%市值>=50亿) 
  2. 按距MA60远近过滤 → 取Top 25
  3. get_kline 逐个获取 -> 计算EMA/ATR → 评分
  4. 输出 底部放量_{date}.json

总API调用: ~26次(1 screener + 25 kline)
"""
import json, os, sys, time
from datetime import datetime
from wudao_client import get_stock_screener, get_kline

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
_RATE_LIMIT = 0.4  # 秒

def calc_ema(vals, n):
    k = 2 / (n + 1)
    e = sum(vals[-n:]) / n
    for v in vals[-(n-1):]:
        e = v * k + e * (1 - k)
    return e

def calc_atr(rows, n=14):
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]['high'], rows[i]['low'], rows[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs: return 0
    return sum(trs[-n:]) / n if len(trs) >= n else sum(trs) / len(trs)

def ema_prev(vals, n):
    k = 2/(n+1); e = sum(vals[-n:])/n
    for v in vals[-(n-1):]: e = v*k + e*(1-k)
    return e

def dir_str(val, prev_val, thr=0.3):
    if prev_val is None or prev_val == 0: return '--'
    return '上升' if ((val - prev_val)/prev_val*100) > thr else ('下降' if ((val - prev_val)/prev_val*100) < -thr else '走平')

def score_stock(s, rows, hot_sectors_set=None):
    if hot_sectors_set is None:
        hot_sectors_set = set()
    detail = {'成交额':0,'MA60位置':0,'板块共振':0,'放量倍数':0,'趋势':0,'基本面':0,'百日新高':0}
    closes = [r['close'] for r in rows]
    today = rows[-1]

    amt = today['amount'] / 1e8
    if amt >= 30: detail['成交额'] = 18
    elif amt >= 20: detail['成交额'] = 14
    elif amt >= 10: detail['成交额'] = 10
    elif amt >= 5: detail['成交额'] = 6
    elif amt >= 3: detail['成交额'] = 4
    else: detail['成交额'] = 2

    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    pct60 = None
    if ma60:
        pct60 = (today['close'] - ma60) / ma60 * 100
        if -3 <= pct60 <= 3: detail['MA60位置'] = 12
        elif -8 <= pct60 <= 8: detail['MA60位置'] = 7
        elif -15 <= pct60 <= 15: detail['MA60位置'] = 3
        else: detail['MA60位置'] = 0

    ind = s.get('industry','')
    detail['板块共振'] = 0
    matched_concepts = []
    concept_to_inds = {
        '芯片概念':['半导体','电子器件','集成电路','分立器件'],
        '5G':['通信设备'],
        '新能源汽车':['汽车配件','汽车整车'],
        '华为概念':['通信设备','软件服务'],
        '机器人概念':['通用机械','自动化设备','机器人'],
        '储能':['电气设备','电源设备'],
        '人工智能':['软件服务'],
        '信创':['软件服务','计算机','IT设备'],
        '光伏':['电气设备','太阳能'],
        '军工':['航空','船舶','航天装备','兵器兵装'],
        '创新药':['化学制药'],
        '医药':['生物制药','医疗器械'],
        '低空经济':['航空','航天装备'],
        '算力':['软件服务','IT设备'],
        '消费电子':['电子器件'],
        '互联网金融':['证券','互联网'],
    }
    for hs in hot_sectors_set:
        if ind and (hs in ind or (ind in hs and len(ind) > 2)):
            matched_concepts.append(hs)
        else:
            matched_inds = concept_to_inds.get(hs, [])
            if ind in matched_inds:
                matched_concepts.append(hs)
    if matched_concepts:
        detail['板块共振'] = 28

    vr = s.get('volumeRatio', 0)
    if vr >= 5: detail['放量倍数'] = 15
    elif vr >= 3: detail['放量倍数'] = 12
    elif vr >= 2: detail['放量倍数'] = 8
    else: detail['放量倍数'] = 0

    detail['趋势'] = 0
    if len(closes) >= 13:
        e5 = calc_ema(closes, 5)
        e13 = calc_ema(closes, 13)
        if len(closes) > 5: e5_prev = ema_prev(closes[:-1], 5)
        if len(closes) > 13: e13_prev = ema_prev(closes[:-1], 13)
        e5d = dir_str(e5, e5_prev if len(closes) > 5 else None, 0.3)
        e13d = dir_str(e13, e13_prev if len(closes) > 13 else None, 0.3)
        if e5d == '上升' and e13d == '上升': detail['趋势'] = 14
        elif e5d == '上升' and e13d != '下降': detail['趋势'] = 7
        elif e5d == '走平' and e13d != '下降': detail['趋势'] = 3

    pe = s.get('peTtm') or 0
    detail['基本面'] = 8 if 0 < pe <= 50 else (4 if 0 < pe <= 100 else 0)

    if len(closes) >= 60 and today['close'] >= max(c for c in closes[-60:]):
        detail['百日新高'] = 5
    elif len(closes) >= 20 and today['close'] >= max(c for c in closes[-20:]):
        detail['百日新高'] = 2

    total = sum(detail.values())
    rating = 'A' if total >= 70 else ('B' if total >= 55 else ('C' if total >= 40 else 'D'))
    notes = []
    if pct60 and pct60 > 15: notes.append('偏离MA60过远')
    if pct60 and pct60 < -15: notes.append('远离MA60')
    if vr > 8: notes.append('放量过猛')
    if detail['趋势'] == 0: notes.append('趋势未转')
    if total < 30: notes.append('综合较差')

    return total, rating, detail, (' '.join(notes) if notes else '趋势未转'), pct60, ma60

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y%m%d')
    print(f'=== 悟道底部放量扫描 {date_str} ===')

    # Step 1: 条件选股
    print('[1/3] 条件选股...')
    params = {
        'date': date_str, 'volumeRatioMin': 2, 'closePctChgMin': 5,
        'amountMinYi': 10, 'excludeST': True, 'sortBy': 'volumeRatio',
        'order': 'desc', 'limit': 100,
    }
    candidates = get_stock_screener(params)
    if not candidates:
        print('无候选')
        return
    print(f'候选 {len(candidates)} 只')

    # 过滤: 距MA60不超过±15%
    filtered = []
    for s in candidates:
        ma60 = s.get('ma60', 0)
        if not ma60:
            continue
        pct60 = (s['close'] - ma60) / ma60 * 100
        if -15 <= pct60 <= 15:  # 只保留在MA60附近的
            filtered.append((s, abs(pct60)))
    filtered.sort(key=lambda x: x[1])
    top_candidates = [x[0] for x in filtered[:25]]
    if not top_candidates:
        print('  无MA60附近候选')
        return
    print(f'  MA60(-15%~+15%): {len(filtered)} 只, 取Top {len(top_candidates)}')
    
    # Step 2: 逐只获取K线
    hot_sectors_set = set()
    try:
        from wudao_client import get_hot_sectors
        sectors = get_hot_sectors(date_str)
        for sec in sectors[:15]:
            if sec.get('name'):
                hot_sectors_set.add(sec['name'])
    except:
        pass
    print(f'[2/3] 获取K线 ({len(top_candidates)} 只)...')
    enriched = []
    for i, s in enumerate(top_candidates):
        code = s['code']
        sys.stdout.write(f'  [{i+1}/{len(top_candidates)}] {s["name"]}({code})...'); sys.stdout.flush()
        time.sleep(_RATE_LIMIT)
        rows = get_kline(code, 65, endDate=date_str)
        if not rows or len(rows) < 20:
            print(' 跳过(数据不足)')
            continue
        print(f' ok')

        closes = [r['close'] for r in rows]
        today = rows[-1]
        total, rating, sdetail, note, pct60, ma60 = score_stock(s, rows, hot_sectors_set)

        ma13 = sum(closes[-13:]) / 13
        ma5 = sum(closes[-5:]) / 5
        e5 = calc_ema(closes, 5)
        e13 = calc_ema(closes, 13)
        atr = calc_atr(rows, 14)

        entry = {
            'code': s.get('tsCode', code),
            'name': s['name'],
            'sector': s.get('industry', ''),
            'close': today['close'],
            'change': today['pct_chg'],
            'amount_yi': round(today['amount'] / 1e8, 1),
            'vol_ratio_vs_60': s.get('volumeRatio', 0),
            'ma60': round(ma60, 2) if ma60 else None,
            'ma13': round(ma13, 2),
            'ma5': round(ma5, 2),
            'ema5': round(e5, 2),
            'ema13': round(e13, 2),
            'atr14': round(atr, 2),
            'date': today['date'][:4]+'-'+today['date'][4:6]+'-'+today['date'][6:8],
            'trade_day': today['date'][:4]+'-'+today['date'][4:6]+'-'+today['date'][6:8],
            'pct_from_ma60': round(pct60, 1) if pct60 else None,
            'pct_from_ma13': round((today['close'] - ma13) / ma13 * 100, 1),
            'pct_from_ma5': round((today['close'] - ma5) / ma5 * 100, 1),
            'pct_from_ema5': round((today['close'] - e5) / e5 * 100, 1),
            'pct_from_ema13': round((today['close'] - e13) / e13 * 100, 1),
            'ma60_dir': '下降', 'ma13_dir': '下降', 'ma5_dir': '下降',
            'ema5_dir': '下降', 'ema13_dir': '下降',
            'score': total, 'rating': rating,
            'score_detail': sdetail, 'risk_note': note,
            'hot_concepts': [],
        }
        entry['hot_concepts'] = matched_concepts[:3] if matched_concepts else []
        entry['sector_in_hot'] = bool(matched_concepts)
        if ma60 and len(closes) >= 60:
            entry['low_60'] = min(r['low'] for r in rows[-60:])
            entry['surge_from_low'] = round((today['close'] - entry['low_60']) / entry['low_60'] * 100, 1)

        enriched.append(entry)

    if not enriched:
        print('无评分候选')
        return

    enriched.sort(key=lambda x: x['score'], reverse=True)
    rating_dist = {}
    for e in enriched:
        rating_dist[e['rating']] = rating_dist.get(e['rating'], 0) + 1

    print(f'\n[3/3] 输出: {len(enriched)} 只, 评分 {rating_dist}')

    output = {
        'trade_day': date_str[:4]+'-'+date_str[4:6]+'-'+date_str[6:8],
        'select_date': datetime.now().strftime('%Y-%m-%d'),
        'market_state': 'uptrend',
        'market_info': {'hs300_close': 0, 'ma20': 0, 'ma60': 0, 'slope': 0.2},
        'mode': '容量核心(悟道)',
        'total_checked': len(candidates),
        'total_bottom_surge': len(enriched),
        'rating_summary': rating_dist,
        'stocks': enriched,
    }

    out = os.path.join(DATA_DIR, f'底部放量_{date_str}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'输出: {out}')
    print(f'\nTop 8:')
    for e in enriched[:8]:
        print(f'  {e["rating"]}({e["score"]:2d}) {e["name"]:>6} {e["code"]:>10} {e["change"]:>+6.2f}% '
              f'量{e["vol_ratio_vs_60"]:.1f}x 额{e["amount_yi"]:.1f}亿 距MA60{e.get("pct_from_ma60","?"):>+5}% {e["sector"]}')

if __name__ == '__main__':
    main()

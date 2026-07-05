# -*- coding: utf-8 -*-
"""Build 6/30 bottom surge pool from collected data"""
import json, os

DATA_DIR = r'C:\Users\Rofis\Desktop\百日新高系统'

concept_to_inds = {
    '芯片概念':['半导体','电子器件','集成电路','分立器件','元器件'],
    '机器人概念':['专用机械','自动化设备','机器人','通用机械'],
    '华为概念':['通信设备','软件服务','元器件'],
    '新能源汽车':['汽车配件','汽车整车'],
    '专精特新':['专用机械','自动化设备','半导体','化工原料','电器仪表'],
    '人工智能':['软件服务','元器件','通信设备'],
    '消费电子概念':['元器件','电子器件'],
    '储能':['电气设备','电源设备'],
    '军工':['航空','船舶','航天装备','兵器兵装'],
    '医药/医疗':['生物制药','医疗器械','医疗保健','医药商业','化学制药','中药','化学制药'],
}

hot_sectors_0630 = {'芯片概念','机器人概念','华为概念','新能源汽车','专精特新','人工智能','消费电子概念','储能'}

stocks = [
    {'code':'300474','name':'景嘉微','industry':'元器件','close':60.48,'ma60':59.89,'vr':2.56,'amt_yi':18.81,'pe':0,'pct_chg':14.01},
    {'code':'000777','name':'中核科技','industry':'机械基件','close':19.54,'ma60':19.71,'vr':2.15,'amt_yi':8.18,'pe':47.6,'pct_chg':5.74},
    {'code':'300434','name':'金石亚药','industry':'化学制药','close':11.23,'ma60':10.24,'vr':2.29,'amt_yi':6.41,'pe':24.4,'pct_chg':3.89},
    {'code':'000566','name':'海南海药','industry':'化学制药','close':4.99,'ma60':4.65,'vr':2.12,'amt_yi':8.94,'pe':0,'pct_chg':9.91},
    {'code':'600468','name':'百利电气','industry':'电气设备','close':6.07,'ma60':7.01,'vr':5.33,'amt_yi':5.23,'pe':79.9,'pct_chg':3.94},
    {'code':'300024','name':'机器人','industry':'专用机械','close':19.33,'ma60':15.65,'vr':2.53,'amt_yi':40.22,'pe':0,'pct_chg':6.80},
]

enriched = []
for s in stocks:
    pct60 = (s['close'] - s['ma60']) / s['ma60'] * 100
    detail = {'成交额':0,'MA60位置':0,'板块共振':0,'放量倍数':0,'趋势':0,'基本面':0,'百日新高':0}

    amt = s['amt_yi']
    if amt >= 30: detail['成交额'] = 18
    elif amt >= 20: detail['成交额'] = 14
    elif amt >= 10: detail['成交额'] = 10
    elif amt >= 5: detail['成交额'] = 6
    elif amt >= 3: detail['成交额'] = 4
    else: detail['成交额'] = 2

    if -3 <= pct60 <= 3: detail['MA60位置'] = 12
    elif -8 <= pct60 <= 8: detail['MA60位置'] = 7
    elif -15 <= pct60 <= 15: detail['MA60位置'] = 3
    else: detail['MA60位置'] = 0

    ind = s['industry']
    matched_concepts = []
    for hs in hot_sectors_0630:
        matched_inds = concept_to_inds.get(hs, [])
        if ind in matched_inds:
            matched_concepts.append(hs)
    if not matched_concepts and ('药' in ind or '医疗' in ind):
        matched_concepts.append('医药/医疗')
    detail['板块共振'] = 28 if matched_concepts else 0

    vr = s['vr']
    if vr >= 5: detail['放量倍数'] = 15
    elif vr >= 3: detail['放量倍数'] = 12
    elif vr >= 2: detail['放量倍数'] = 8
    else: detail['放量倍数'] = 0

    pctchg = s['pct_chg']
    if pctchg > 5 and vr >= 2 and -8 <= pct60 <= 8:
        detail['趋势'] = 14
    elif pctchg > 3 and vr >= 1.5:
        detail['趋势'] = 7
    elif -3 <= pct60 <= 3 and vr >= 1.5:
        detail['趋势'] = 3
    else:
        detail['趋势'] = 0

    pe = s.get('pe', 0)
    if 0 < pe <= 50: detail['基本面'] = 8
    elif 0 < pe <= 100: detail['基本面'] = 4
    else: detail['基本面'] = 0

    total = sum(detail.values())
    rating = 'A' if total >= 70 else ('B' if total >= 55 else ('C' if total >= 40 else 'D'))

    notes = []
    if pct60 > 15: notes.append('偏离MA60过远')
    if pct60 < -15: notes.append('远离MA60')
    if vr > 8: notes.append('放量过猛')
    if detail['趋势'] == 0: notes.append('趋势未转')
    if total < 30: notes.append('综合较差')

    enriched.append({
        'code': s['code'],
        'name': s['name'],
        'sector': s['industry'],
        'close': s['close'],
        'change': s['pct_chg'],
        'amount_yi': s['amt_yi'],
        'vol_ratio_vs_60': s['vr'],
        'ma60': s['ma60'],
        'pct_from_ma60': round(pct60, 1),
        'score': total,
        'rating': rating,
        'score_detail': detail,
        'risk_note': ' '.join(notes) if notes else '趋势未转',
        'sector_in_hot': bool(matched_concepts),
        'hot_concepts': matched_concepts[:3],
        'trade_day': '2026-06-30',
    })

enriched.sort(key=lambda x: x['score'], reverse=True)
rating_dist = {}
for e in enriched:
    rating_dist[e['rating']] = rating_dist.get(e['rating'], 0) + 1

output = {
    'trade_day': '2026-06-30',
    'select_date': '2026-06-30',
    'market_state': 'uptrend',
    'mode': '容量核心(悟道API)',
    'total_checked': len(enriched),
    'total_bottom_surge': len(enriched),
    'rating_summary': rating_dist,
    'stocks': enriched,
}

out_path = os.path.join(DATA_DIR, '底部放量_20260630.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'输出: {out_path}')
for e in enriched:
    c = ','.join(e['hot_concepts']) if e['hot_concepts'] else '-'
    print(f'  {e["rating"]}({e["score"]:2d}) {e["name"]:>6} {e["code"]:>8} MA60{e["pct_from_ma60"]:>+5}% VR{e["vol_ratio_vs_60"]:.1f}x 额{e["amount_yi"]:.1f}亿 {e["sector"]:>8} {c}')
    print(f'    {e["risk_note"]}')
print(f'评分分布: {rating_dist}')

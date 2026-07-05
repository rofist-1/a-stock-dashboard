# -*- coding: utf-8 -*-
"""Scan results scoring and output for 20260629"""
import json, os

DATA_DIR = r'C:\Users\Rofis\Desktop\百日新高系统'

concept_to_inds = {
    '芯片概念':['半导体','电子器件','集成电路','分立器件'],
    '新能源汽车':['汽车配件','汽车整车'],
    '华为概念':['通信设备','软件服务'],
    '机器人概念':['通用机械','自动化设备','机器人'],
    '储能':['电气设备','电源设备'],
    '人工智能':['软件服务'],
    '信创':['软件服务','计算机','IT设备'],
    '光伏':['电气设备','太阳能'],
    '军工':['航空','船舶','航天装备','兵器兵装'],
    '创新药':['化学制药'],
    '医疗器械概念':['医疗器械'],
    '医药/医疗':['生物制药','医疗器械','医疗保健','医药商业','化学制药','中药'],
    '低空经济':['航空','航天装备'],
    '算力':['软件服务','IT设备'],
    '消费电子':['电子器件'],
    '互联网金融':['证券','互联网'],
}

hot_sectors = {'芯片概念','创新药','专精特新','一带一路','新能源汽车','仿制药一致性评价','2025年报预增','医疗器械概念'}

stocks = [
    {'code':'301263','name':'泰恩康','industry':'医药商业','close':21.33,'ma60':21.76,'vr':3.31,'amt_yi':5.32,'pe':424,'pct_chg':18.17},
    {'code':'000521','name':'长虹美菱','industry':'家用电器','close':5.49,'ma60':5.47,'vr':4.38,'amt_yi':2.03,'pe':18.9,'pct_chg':10.02},
    {'code':'688122','name':'西部超导','industry':'小金属','close':60.00,'ma60':65.61,'vr':2.89,'amt_yi':26.84,'pe':54.7,'pct_chg':12.99},
    {'code':'000404','name':'长虹华意','industry':'家用电器','close':8.06,'ma60':7.76,'vr':3.70,'amt_yi':3.44,'pe':11.0,'pct_chg':8.77},
    {'code':'605296','name':'神农集团','industry':'农业综合','close':28.80,'ma60':28.06,'vr':3.40,'amt_yi':2.52,'pe':0,'pct_chg':5.77},
    {'code':'001289','name':'龙源电力','industry':'新型电力','close':16.12,'ma60':16.92,'vr':4.84,'amt_yi':5.13,'pe':31.7,'pct_chg':-8.25},
    {'code':'000623','name':'吉林敖东','industry':'中药材','close':18.10,'ma60':18.22,'vr':1.61,'amt_yi':2.79,'pe':0,'pct_chg':3.19},
    {'code':'301393','name':'昊帆生物','industry':'化工原料','close':63.10,'ma60':56.24,'vr':3.12,'amt_yi':4.21,'pe':60.2,'pct_chg':12.47},
    {'code':'688193','name':'仁度生物','industry':'医疗保健','close':55.30,'ma60':52.46,'vr':3.01,'amt_yi':0.95,'pe':160,'pct_chg':3.73},
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
    for hs in hot_sectors:
        matched_inds = concept_to_inds.get(hs, [])
        if ind in matched_inds:
            matched_concepts.append(hs)
    for med_kw in ['医药','医疗','生物','药']:
        if med_kw in ind:
            if '创新药' in hot_sectors or '医疗器械概念' in hot_sectors:
                matched_concepts.append('医药/医疗')
            break
    
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
    })

enriched.sort(key=lambda x: x['score'], reverse=True)
rating_dist = {}
for e in enriched:
    rating_dist[e['rating']] = rating_dist.get(e['rating'], 0) + 1

print('='*65)
print('  底部放量扫描 20260629 (悟道API)')
print('='*65)
print(f'  共 {len(enriched)} 只候选')
print(f'  评分分布: {rating_dist}')
print('-'*65)
print(f'  {"评":>2} {"分":>2} {"名称":>8} {"代码":>8} {"MA60":>6} {"VR":>4} {"额(亿)":>6} {"概念"}')
print('-'*65)
for e in enriched:
    c = ','.join(e['hot_concepts']) if e['hot_concepts'] else '-'
    print(f'  {e["rating"]} {e["score"]:2d} {e["name"]:>8} {e["code"]:>8} {e["pct_from_ma60"]:>+5}% {e["vol_ratio_vs_60"]:.1f}x {e["amount_yi"]:>5.1f} {c}')
    print(f'     {e["risk_note"]}')

output = {
    'trade_day': '2026-06-29',
    'select_date': '2026-06-29',
    'market_state': 'unknown',
    'mode': '容量核心(悟道API)',
    'total_checked': len(enriched),
    'total_bottom_surge': len(enriched),
    'rating_summary': rating_dist,
    'stocks': enriched,
}

out_path = os.path.join(DATA_DIR, '底部放量_20260629.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\n输出: {out_path}')

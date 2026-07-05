# -*- coding: utf-8 -*-
"""Build 6/26 bottom surge pool from collected data"""
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
    '商业航天':['航空','航天装备'],
}

hot_sectors_0626 = {'芯片概念','专精特新','商业航天','储能','光伏概念','军工','华为概念','一带一路'}

stocks = [
    {'code':'002202','name':'金风科技','industry':'电气设备','close':23.33,'ma60':25.5,'vr':2.24,'amt_yi':70.15,'pe':0,'pct_chg':6.53},
    {'code':'600660','name':'福耀玻璃','industry':'汽车配件','close':50.43,'ma60':55.0,'vr':2.29,'amt_yi':15.08,'pe':0,'pct_chg':5.04},
    {'code':'300102','name':'乾照光电','industry':'半导体','close':24.34,'ma60':27.5,'vr':3.08,'amt_yi':25.8,'pe':0,'pct_chg':9.84},
    {'code':'002335','name':'科华数据','industry':'电气设备','close':43.62,'ma60':52.0,'vr':2.53,'amt_yi':42.89,'pe':0,'pct_chg':3.24},
    {'code':'605366','name':'宏柏新材','industry':'化工原料','close':14.38,'ma60':11.4,'vr':4.31,'amt_yi':21.55,'pe':0,'pct_chg':10.02},
    {'code':'000703','name':'恒逸石化','industry':'化纤','close':16.67,'ma60':14.3,'vr':3.00,'amt_yi':40.38,'pe':28.9,'pct_chg':7.34},
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
    for hs in hot_sectors_0626:
        matched_inds = concept_to_inds.get(hs, [])
        if ind in matched_inds:
            matched_concepts.append(hs)
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
        'trade_day': '2026-06-26',
    })

enriched.sort(key=lambda x: x['score'], reverse=True)
rating_dist = {}
for e in enriched:
    rating_dist[e['rating']] = rating_dist.get(e['rating'], 0) + 1

print('='*65)
print('  底部放量扫描 20260626 (悟道API)')
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
    'trade_day': '2026-06-26',
    'select_date': '2026-06-26',
    'market_state': 'downtrend',
    'mode': '容量核心(悟道API)',
    'total_checked': len(enriched),
    'total_bottom_surge': len(enriched),
    'rating_summary': rating_dist,
    'stocks': enriched,
}

out_path = os.path.join(DATA_DIR, '底部放量_20260626.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\n输出: {out_path}')

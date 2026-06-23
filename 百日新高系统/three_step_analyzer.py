# -*- coding: utf-8 -*-
"""
三步筛选法分析模块
=================
定出身 → 看标签 → 判位置

数据源：wudao_client + kline_cache
"""

import json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wudao_client import search_stock, get_hot_sectors, get_limit_up_filter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, 'kline_cache')
TODAY = datetime.now().strftime('%Y%m%d')

INDUSTRY_CHAIN_MAP = {
    # 上游（材料/设备）
    '有色': '上游', '钢铁': '上游', '煤炭': '上游', '化工': '上游',
    '材料': '上游', '采掘': '上游', '石油': '上游', '矿业': '上游',
    '硅料': '上游', '锂矿': '上游', '稀土': '上游', '半导体设备': '上游',
    '光伏设备': '上游', '风电设备': '上游',
    # 中游（核心制造）
    '半导体': '中游', '芯片': '中游', '电子': '中游', '元器件': '中游',
    '电池': '中游', '制造': '中游', '机械': '中游', '汽车': '中游',
    '电气': '中游', '通信': '中游', '软件': '中游', '计算机': '中游',
    '军工': '中游', '医药': '中游', '生物': '中游',
    # 下游（应用/终端）
    '新能源车': '下游', '整车': '下游', '消费': '下游', '家电': '下游',
    '食品': '下游', '饮料': '下游', '服装': '下游', '地产': '下游',
    '建筑': '下游', '交通': '下游', '物流': '下游', '零售': '下游',
    '传媒': '下游', '游戏': '下游', '教育': '下游', '医疗': '下游',
    '金融': '下游', '券商': '下游', '银行': '下游', '保险': '下游',
}


def load_kline(code):
    """从 kline_cache 加载某只股票的日K数据"""
    prefix_map = {'6': 'sh', '0': 'sz', '3': 'sz', '4': 'bj', '8': 'bj'}
    prefix = prefix_map.get(code[0], 'sh')
    fp = os.path.join(CACHE_DIR, f'{prefix}{code[-6:]}.pkl')
    if not os.path.exists(fp):
        return None
    import pickle
    with open(fp, 'rb') as f:
        kd = pickle.load(f)
    df = kd.get('df')
    if df is None or len(df) < 20:
        return None
    return df


def calc_ma(closes, n):
    if len(closes) < n: return None
    return sum(closes[-n:]) / n


def compute_indicators(df):
    """计算技术指标（均价线、距离MA60等）"""
    closes = df['close'].tolist()
    highs = df['high'].tolist()
    lows = df['low'].tolist()
    last_close = closes[-1]
    ma5 = calc_ma(closes, 5)
    ma13 = calc_ma(closes, 13)
    ma60 = calc_ma(closes, 60)
    pct_ma60 = round((last_close - ma60) / ma60 * 100, 1) if ma60 else None
    # ATR
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr14 = round(sum(tr[-14:])/14, 2) if len(tr) >= 14 else None
    return {
        'close': round(last_close, 2),
        'ma5': round(ma5, 2) if ma5 else None,
        'ma13': round(ma13, 2) if ma13 else None,
        'ma60': round(ma60, 2) if ma60 else None,
        'pct_from_ma60': pct_ma60,
        'atr14': atr14,
    }


def get_mainlines(date_str=TODAY):
    """获取当日市场最强主线（涨停集中度最高的板块 + 连板高度方向）"""
    sectors = get_hot_sectors(date_str)
    mainlines = []
    for s in sectors[:5]:
        mainlines.append({
            'name': s.get('name', ''),
            'limit_up_num': s.get('limitUpNum', 0),
            'high_board': s.get('highBoard', 0),
            'stocks': [st.get('name','') for st in s.get('stocks', [])[:3]],
        })
    # 从涨停池识别最高连板方向
    tops = get_limit_up_filter(date_str, 100)
    max_continue = 0
    max_continue_name = ''
    max_reason = ''
    for t in tops:
        cn = t.get('continue_num', 0) or 0
        if cn > max_continue:
            max_continue = cn
            max_continue_name = t.get('name', '')
            max_reason = t.get('reason_type', '')
    return {
        'hot_sectors': mainlines,
        'highest_board': {
            'stock': max_continue_name,
            'continue_num': max_continue,
            'reason': max_reason,
        }
    }


def chain_position(industry, reason_type=''):
    """判断产业链位置"""
    text = f'{industry} {reason_type}'
    for kw, pos in INDUSTRY_CHAIN_MAP.items():
        if kw in text:
            return pos
    return '不明（需人工判断）'


def analyze_stock(code_or_name: str) -> dict:
    """三步筛选分析主入口"""
    result = {'code': code_or_name, 'time': datetime.now().strftime('%H:%M:%S')}

    # 第〇步：搜索股票
    info = search_stock(code_or_name)
    if not info:
        result['error'] = f'未找到股票: {code_or_name}'
        return result
    stock = info[0]
    code = stock.get('symbol') or stock.get('code', code_or_name)
    name = stock.get('name', '')
    industry = stock.get('industry', '')
    area = stock.get('area', '')
    result['code'] = code
    result['name'] = name
    result['basic'] = {'industry': industry, 'area': area, 'market': stock.get('market', '')}

    # 第一步：定出身
    result['step1_business'] = {
        'industry': industry,
        'area': area,
        'conclusion': f'{name}主营行业: {industry}（{area}地区）',
    }

    # 第二步：看标签
    # 用行业名作为核心标签，从涨停池中找相关主线做匹配
    mainlines = get_mainlines()
    # 生成标签列表：行业名 + 涨停原因中可能的关联
    tags_list = [industry]
    # 补充：从涨停池里找与该股行业相关的标志
    for s in mainlines.get('hot_sectors', []):
        sn = s.get('name', '')
        if industry in sn or sn in industry:
            tags_list.append(sn)
    # 去重
    tags_list = list(dict.fromkeys(tags_list))
    matched = []
    unmatched = []
    hot_names = [s['name'] for s in mainlines.get('hot_sectors', [])]
    for tag in tags_list:
        is_match = any(tag in hn or hn in tag for hn in hot_names if hn)
        stars = 4 if is_match else 2
        (matched if is_match else unmatched).append({'tag': tag, 'stars': stars, 'match_mainline': is_match})
    result['step2_tags'] = {
        'tags': matched + unmatched,
        'mainlines': mainlines,
        'best_tag': matched[0]['tag'] if matched else (tags_list[0] if tags_list else '--'),
        'stale_tag': unmatched[-1]['tag'] if unmatched else None,
    }

    # 第三步：判位置
    chain = chain_position(industry)
    # 当前市场对产业链各位置的偏好（从热点板块推断）
    hot_chain_prefs = {'上游': 0, '中游': 0, '下游': 0}
    for s in mainlines.get('hot_sectors', []):
        sn = s['name']
        for ck, cp in INDUSTRY_CHAIN_MAP.items():
            if ck in sn:
                hot_chain_prefs[cp] = hot_chain_prefs.get(cp, 0) + s.get('limit_up_num', 0)
    chain_pref = max(hot_chain_prefs, key=hot_chain_prefs.get) if max(hot_chain_prefs.values()) > 0 else '均衡'
    result['step3_position'] = {
        'chain': chain,
        'market_preference': chain_pref,
        'chain_pref_detail': hot_chain_prefs,
        'suitable': chain == chain_pref or chain == '中游',
    }

    # 技术面数据
    kl = load_kline(code)
    if kl is not None and not kl.empty:
        result['technical'] = compute_indicators(kl)
    else:
        result['technical'] = {'error': 'kline数据不足'}

    # 综合评估
    best_tag = result['step2_tags']['best_tag']
    is_mainline = bool(matched)
    position_ok = result['step3_position']['suitable']
    tech_ok = result['technical'].get('pct_from_ma60') is not None and -5 < result['technical']['pct_from_ma60'] < 15

    if is_mainline and position_ok and tech_ok:
        pos_type = '核心底仓'
    elif is_mainline:
        pos_type = '卫星仓位'
    elif position_ok:
        pos_type = '独立配置'
    else:
        pos_type = '不宜参与'
    result['summary'] = {
        'position_type': pos_type,
        'position_advice': {
            '核心底仓': '可作为组合核心标的，放量回踩MA60时布局',
            '卫星仓位': '有热点催化但位置或产业链不占优，小仓博弈',
            '独立配置': '不在当前主线内，但基本面或位置较好，独立持有',
            '不宜参与': '产业链位置不利且无热点催化，等待更好机会',
        }.get(pos_type, ''),
        'verify_signals': [
            '① 放量站上MA5',
            '② 所属板块涨停数增加',
            '③ 龙虎榜有机构/游资介入',
        ],
    }

    return result


if __name__ == '__main__':
    import sys as _sys
    query = _sys.argv[1] if len(_sys.argv) > 1 else '600171'
    out = analyze_stock(query)
    out['_note'] = '三步筛选分析 | 数据仅供参考，不构成投资建议'
    print(json.dumps(out, ensure_ascii=False, indent=2))

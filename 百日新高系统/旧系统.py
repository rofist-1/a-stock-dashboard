# -*- coding: utf-8 -*-
"""
换股系统 v2.0 - 基于新条件的每日选股
==================
数据源：悟道API + 本地缓存
换股条件：
1. 股价站上60日均线 (aboveMa:[60])
2. 首次突破已经过去3~5天 (调整期)
3. 调整期间量比回落 < 1.5 (缩量)
4. 当前再次放量 ≥ 1.2 (再启动)
5. 流通市值 ≥ 100亿 (去小盘一日游)
6. 收盘价仍在MA60上方 (回踩不破)
"""
import json, os, sys, time
from datetime import datetime
from collections import defaultdict

_script_dir = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = _script_dir

# 辅助函数
def log(msg):
    print(msg, flush=True)

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default

def calc_sma(values, n):
    if not values or len(values) < n:
        return None
    return sum(values[-n:]) / n

def get_sector_map():
    """加载行业映射表"""
    path = os.path.join(DATA_DIR, '百日新高系统', 'sector_map.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def get_stock_list():
    """加载股票列表"""
    path = os.path.join(DATA_DIR, '百日新高系统', 'stock_list.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def get_kline(code, days=80):
    """获取K线数据"""
    try:
        from wudao_client_ext import _get
        resp = _get('kline', {'code': code, 'days': days})
        d = resp.get('data', {})
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return d.get('rows', d.get('data', []))
    except:
        pass
    return []

def get_stock_screener(params):
    """条件选股"""
    try:
        from wudao_client_ext import get_stock_screener
        return get_stock_screener(params)
    except:
        return []

def get_market_overview(date):
    """获取市场概况"""
    try:
        from wudao_client_ext import get_market_overview
        return get_market_overview(date)
    except:
        return {}

def get_stock_research(query):
    """搜索股票"""
    try:
        from wudao_client_ext import _get
        resp = _get('search', {'query': query})
        return resp.get('data', {}).get('items', [])
    except:
        return []

def run(date=None, output_file=None):
    date = date or datetime.now().strftime('%Y%m%d')
    display_date = f'{date[:4]}-{date[4:6]}-{date[6:8]}'

    print('=' * 60)
    print(f'  换股系统 v2.0')
    print(f'  日期: {display_date}')
    print('=' * 60)
    print()

    # 加载行业映射和股票列表
    sector_map = get_sector_map()
    stock_list = get_stock_list()

    # 获取市场概况
    market = get_market_overview(date)
    rise = int(market.get('rise_count', 0))
    fall = int(market.get('fall_count', 0))
    total = rise + fall
    rise_ratio = (rise / total * 100) if total > 0 else 0

    log('[模块一] 大盘环境判断...')

    # 计算市场温度和仓位策略
    if rise_ratio > 70:
        market_type = '上涨市'
        position_limit = '7-10成'
        position_note = '积极参与'
    elif rise_ratio < 30:
        market_type = '下跌市'
        position_limit = '0-1成'
        position_note = '强制空仓'
    else:
        market_type = '震荡市'
        position_limit = '3-5成'
        position_note = '只低吸'

    log(f'  市场状态: {market_type}')
    log(f'  仓位限制: {position_limit}')

    # 获取突破后的股票
    log('[模块二] 获取突破后股票...')
    candidates = []
    for stock in stock_list:
        code = stock.get('code', '')
        if not code or len(code) != 6:
            continue

        klines = get_kline(code, 80)
        if len(klines) < 60:
            continue

        closes = [safe_float(k['close']) for k in klines]
        current_close = safe_float(klines[-1].get('close', 0))
        ma60 = calc_sma(closes, 60)

        if not ma60 or current_close < ma60 * 0.98:
            continue

        # 1. 在最后5-15天内找首次突破
        first_break_idx = None
        first_break_vol = 0
        search_range = min(len(klines) - 2, 17)

        for lookback in range(3, search_range + 1):
            i = len(klines) - 1 - lookback
            if i < 60:
                continue

            curr_close_i = safe_float(klines[i].get('close', 0))
            prev_close_i = safe_float(klines[i-1].get('close', 0))
            vol_i = safe_float(klines[i].get('volume', 0))

            window_60 = closes[i-59:i+1]
            if len(window_60) < 60:
                continue
            ma60_i = sum(window_60) / 60

            avg_vol_before = sum(safe_float(klines[j].get('volume', 0)) for j in range(max(0, i-5), i)) / 5
            if avg_vol_before > 0 and prev_close_i < ma60_i and curr_close_i > ma60_i:
                if vol_i / avg_vol_before >= 1.3:
                    first_break_idx = i
                    first_break_vol = vol_i
                    break

        if first_break_idx is None:
            continue

        # 2. 计算调整期间平均量比
        adjustment_start = first_break_idx + 1
        adjustment_end = min(adjustment_start + 5, len(klines) - 1)
        adjustment_vols = []
        for j in range(adjustment_start, adjustment_end + 1):
            vol = safe_float(klines[j].get('volume', 0))
            if vol > 0:
                adjustment_vols.append(vol)

        if not adjustment_vols:
            continue

        avg_adjustment_vol = sum(adjustment_vols) / len(adjustment_vols)
        current_vol = safe_float(klines[-1].get('volume', 0))

        # 3. 检查缩量条件 (< 1.5倍)
        vol_ratio_during_adjustment = avg_adjustment_vol / max(first_break_vol, 1) if first_break_vol > 0 else 1
        if vol_ratio_during_adjustment > 1.5:
            continue

        # 4. 检查当前是否有再次放量 (≥ 1.2倍)
        max_recent_vol = max(adjustment_vols) if adjustment_vols else current_vol
        vol_ratio_current = current_vol / max_recent_vol if max_recent_vol > 0 else 1
        if vol_ratio_current < 1.2:
            continue

        # 5. 检查流通市值 >= 100亿
        market_cap_info = stock.get('market_cap_info', {})
        market_cap_str = market_cap_info.get('circ', '0')
        market_cap_yi = safe_float(market_cap_str)
        if market_cap_yi < 100:
            continue

        # 6. 确保收盘价仍在MA60上方
        if current_close < ma60 * 0.98:
            continue

        candidates.append({
            'code': code,
            'name': stock.get('name', ''),
            'industry': sector_map.get(code, '未知'),
            'current_close': current_close,
            'pct_chg': safe_float(klines[-1].get('pct_chg', 0)),
            'ma60': ma60,
            'first_break_idx': first_break_idx,
            'vol_ratio_during_adjustment': vol_ratio_during_adjustment,
            'vol_ratio_current': vol_ratio_current,
            'market_cap_yi': market_cap_yi,
        })

    log(f'  符合条件的股票: {len(candidates)} 只')

    # 生成报告
    report = f'''# 每日选股简报 — {display_date}
> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 一、大盘环境
- 市场状态: {market_type}
- 涨跌比: {rise}:{fall} ({rise_ratio:.1f}%)

## 二、符合新换股条件的股票
> 共 {len(candidates)} 只股票符合所有筛选条件

| 代码 | 名称 | 板块 | 收盘价 | 涨幅 | 首次突破日 | 调整量比 | 当前量比 | 流通市值(亿) |
|------|------|------|--------|------|-------------|-------------|-------------|------------|
'''

    for c in candidates:
        break_date = klines[c['first_break_idx']]['date'] if c['first_break_idx'] < len(klines) else 'N/A'
        report += f'''| {c['code']} | {c['name']} | {c['industry']} | {c['current_close']} | {c['pct_chg']:+.2f}% | {break_date} | {c['vol_ratio_during_adjustment']:.2f}x | {c['vol_ratio_current']:.2f}x | {c['market_cap_yi']:.1f} |
'''

    report += '''
---
**风险提示**：本报告仅提供技术形态筛选参考，不构成投资建议。所有信号均需次日开盘后确认，请结合个人风险承受能力决策。'''

    print('\n' + '=' * 60)
    print(report)

    # 保存报告
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        log(f'\n报告已保存到: {output_file}')

    # 保存JSON结果
    json_path = os.path.join(DATA_DIR, f'换股结果_{date}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date,
            'candidates': candidates,
            'market_state': market_type,
            'rise_ratio': rise_ratio,
        }, f, ensure_ascii=False, indent=2)

    return report

def main():
    date = None
    output_file = None

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--date' and i + 1 < len(sys.argv):
            date = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--output' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    run(date=date, output_file=output_file)

if __name__ == '__main__':
    main()

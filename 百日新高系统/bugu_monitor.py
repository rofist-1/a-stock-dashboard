# -*- coding: utf-8 -*-
"""
主线补涨监测 (悟道API增强版)
==========================
基于通达信导出数据，筛选芯片/机器人主线内的底部补涨+趋势中继标的。
使用悟道 API 替换 sector_map.json 行业匹配，并 enriched 涨停原因/连板数。

数据源：
  1. (主) 通达信导出 xlsx — 全市场扫描（5526+只）
  2. (辅) 悟道 API limit-up filter — 为涨停标的补充涨停原因/连板数

输出: bugu_YYYYMMDD.json 供看板渲染

条件:
  模型一(底部补涨): 涨幅>5%, 10日涨幅<15%, 量比>0.5
  模型二(趋势中继): 涨幅>5%, 10日涨幅5~30%, 量比>0.5
"""

import sys, os, json, io, re, time
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.dirname(DATA_DIR)  # Desktop

sys.path.insert(0, DATA_DIR)
from wudao_client import get_limit_up_filter

# 加载板块映射（行业回退）
_SECTOR_MAP_PATH = os.path.join(DATA_DIR, 'sector_map.json')
_SECTOR_MAP = {}
if os.path.exists(_SECTOR_MAP_PATH):
    try:
        with open(_SECTOR_MAP_PATH, 'r', encoding='utf-8') as f:
            _SECTOR_MAP = json.load(f)
        print(f'[INFO] 加载板块映射: {len(_SECTOR_MAP)}只')
    except:
        pass

# 主线行业定义
CHIP_INDUSTRIES = {'电子器件', '电子信息', '半导体', '元器件'}
ROBOT_INDUSTRIES = {'机械行业', '专用机械', '电器仪表', '纺织机械', '通用机械'}

# 主线关键词
CHIP_KW = ['芯片','半导体','晶圆','封测','光刻','靶材','硅片','集成电路','存储','先进封装','PCB','铜箔','覆铜板','MLPC']
ROBOT_KW = ['机器人','减速器','伺服','数控','机器视觉','工业母机','机床','人形','机器视觉']


def find_latest_export():
    """找最新通达信导出 xlsx"""
    import glob as _g
    files = _g.glob(os.path.join(EXPORT_DIR, '全部A股*.xlsx'))
    if not files:
        files = _g.glob(os.path.join(EXPORT_DIR, '*A股*.xlsx'))
    if not files:
        files = _g.glob(os.path.join(EXPORT_DIR, '*.xlsx'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def match_mainline(name, industry):
    """判断是否属于芯片/机器人主线。优先用 industry，其次按名称关键词。"""
    n = str(name)
    ind = str(industry)

    is_chip = ind in CHIP_INDUSTRIES
    is_robot = ind in ROBOT_INDUSTRIES

    for kw in CHIP_KW:
        if kw in n:
            is_chip = True
    for kw in ROBOT_KW:
        if kw in n:
            is_robot = True

    return is_chip, is_robot


def main():
    import pandas as pd

    # 0. 确定 trade_day 和 select_date
    select_date = datetime.now().strftime('%Y-%m-%d')
    script_start = datetime.now().strftime('%Y-%m-%d %H:%M')
    # 通达信导出的日期从文件名推断（通常是前一日), 若无则用今天
    today_str = datetime.now().strftime('%Y%m%d')

    # 1. 找通达信导出文件
    xlsx_path = find_latest_export()
    if not xlsx_path:
        print('[ERROR] 未找到通达信导出文件')
        return
    print(f'[INFO] 数据源: {os.path.basename(xlsx_path)}')

    # 从文件名推断 trade_day：通达信导出文件名含日期
    import re as _re
    fname = os.path.basename(xlsx_path)
    m = _re.search(r'(\d{4}-\d{2}-\d{2})|(\d{8})', fname)
    if m:
        raw = m.group(1) or m.group(2)
        if len(raw) == 8:
            trade_day = f'{raw[:4]}-{raw[4:6]}-{raw[6:8]}'
        else:
            trade_day = raw
    else:
        trade_day = datetime.now().strftime('%Y-%m-%d')
    trade_day_str = trade_day.replace('-', '')
    print(f'[INFO] 行情交易日: {trade_day}  |  选股执行日: {select_date}')

    df = pd.read_excel(xlsx_path)
    cols = [c.strip() for c in df.columns]
    print(f'[INFO] 列数: {len(cols)}, 总行: {len(df)}')

    # 列映射 (通达信固定顺序)
    c_code, c_name, c_chg, c_close = cols[0], cols[1], cols[2], cols[3]
    c_chg10, c_vr, c_chg20 = cols[8], cols[11], cols[14]

    # 2. 获取悟道涨停池（用于 enrich）
    today_str = datetime.now().strftime('%Y%m%d')
    today_display = datetime.now().strftime('%Y-%m-%d')
    limit_up_lookup = {}
    try:
        lu_stocks = get_limit_up_filter(date=today_str, limit=200)
        for s in lu_stocks:
            code_clean = str(s.get("code", "")).replace(".SH","").replace(".SZ","").replace(".BJ","").strip()
            if code_clean:
                limit_up_lookup[code_clean] = {
                    "reason_type": str(s.get("reason_type", "")),
                    "continue_num": int(s.get("continue_num", 0) or 0),
                    "order_amount": float(s.get("order_amount", 0) or 0),
                    "industry": str(s.get("industry", "")),
                    "limit_up_type": str(s.get("limit_up_type", "")),
                }
        print(f'[INFO] 悟道涨停池: {len(lu_stocks)}只, 匹配用于 enrich')
    except Exception as e:
        print(f'[WARN] 悟道 API 获取失败(不影响主流程): {e}')

    m1_stocks = []  # 模型一：底部补涨
    m2_stocks = []  # 模型二：趋势中继

    for _, row in df.iterrows():
        try:
            code = str(row[c_code]).strip()
            name = str(row[c_name]).strip()
            chg = float(str(row[c_chg]).replace('%', '').strip())
        except:
            continue
        if chg < 5:
            continue

        # 补齐代码后缀
        if code.startswith('6') or code.startswith('68'):
            code_full = code + '.SH'
        elif code.startswith('0') or code.startswith('3'):
            code_full = code + '.SZ'
        elif code.startswith('8'):
            code_full = code + '.BJ'
        else:
            code_full = code

        # 行业：优先从悟道涨停池获取，否则从 sector_map.json 回退
        industry = ""
        if code in limit_up_lookup:
            industry = limit_up_lookup[code].get("industry", "")
        if not industry:
            code_map = code.zfill(6)
            industry = _SECTOR_MAP.get(code_map, '') or _SECTOR_MAP.get(code, '') or ''

        is_chip, is_robot = match_mainline(name, industry)
        if not is_chip and not is_robot:
            continue

        try:
            chg10 = float(str(row[c_chg10]).replace('%', '').strip())
        except:
            chg10 = 0
        try:
            vr = float(str(row[c_vr]).strip())
        except:
            vr = 0
        try:
            close = float(str(row[c_close]).strip())
        except:
            close = 0

        mainline = '芯片' if is_chip else ''
        if is_robot:
            mainline = mainline + '+机器人' if mainline else '机器人'

        # 悟道 enrich
        lu_info = limit_up_lookup.get(code, {})
        reason_type = lu_info.get("reason_type", "")
        continue_num = lu_info.get("continue_num", 0)
        order_amount = lu_info.get("order_amount", 0)
        limit_up_type = lu_info.get("limit_up_type", "")

        item = {
            'code': code_full, 'code_short': code, 'name': name,
            'change': round(chg, 2), 'chg10': round(chg10, 2),
            'vol_ratio': round(vr, 2), 'close': close,
            'industry': industry, 'mainline': mainline,
            'reason_type': reason_type,
            'continue_num': continue_num,
            'order_amount': order_amount,
            'limit_up_type': limit_up_type,
            'trade_day': trade_day,
            'select_date': select_date,
        }

        # 模型一：底部补涨
        if chg10 < 15 and vr >= 0.5:
            item['model'] = 1
            item['model_label'] = '底部补涨'
            if chg >= 9.5 and continue_num >= 1:
                item['note'] = f'首板启动({reason_type[:20]})' if reason_type else '首板启动'
            elif chg10 < 3:
                item['note'] = '底部首板'
            else:
                item['note'] = '刚启动'
            m1_stocks.append(item.copy())

        # 模型二：趋势中继
        if 5 <= chg10 <= 30 and vr >= 0.5:
            item['model'] = 2
            item['model_label'] = '趋势中继'
            if chg >= 9.5 and continue_num >= 2:
                item['note'] = f'{continue_num}连板突破({reason_type[:20]})' if reason_type else f'{continue_num}连板突破'
            elif chg >= 9.5:
                item['note'] = '涨停突破'
            else:
                item['note'] = '趋势加速'
            m2_stocks.append(item.copy())

    # 去重
    seen = set()
    all_stocks = []
    for s in m1_stocks + m2_stocks:
        key = s['code']
        if key in seen:
            continue
        seen.add(key)
        all_stocks.append(s)

    # 质量评级(用涨停数据 as heuristic)
    for s in all_stocks:
        if s['continue_num'] >= 3:
            s['quality'] = 'A'
        elif s['continue_num'] >= 1:
            s['quality'] = 'B'
        elif s['vol_ratio'] >= 2:
            s['quality'] = 'B'
        else:
            s['quality'] = 'C'

    # 板块信息(从 data.json 主线获取)
    data_json_path = os.path.join(EXPORT_DIR, 'data.json')
    hot_sectors = []
    if os.path.exists(data_json_path):
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                dj = json.load(f)
            if dj:
                latest = dj[-1]
                for k in ['s1Name','s2Name','s3Name']:
                    v = latest.get(k, '')
                    if v:
                        hot_sectors.append(v)
        except:
            pass

    output = {
        'trade_day': trade_day,
        'select_date': select_date,
        'total_checked': len(df),
        'total_m1': len(m1_stocks),
        'total_m2': len(m2_stocks),
        'total_unique': len(all_stocks),
        'hot_mainlines': hot_sectors,
        'm1_stocks': m1_stocks,
        'm2_stocks': m2_stocks,
        'stocks': all_stocks,
    }

    out_path = os.path.join(DATA_DIR, f'bugu_{trade_day_str}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'[INFO] 输出: {out_path}')
    print(f'[INFO] 模型一(底部补涨): {len(m1_stocks)}只')
    print(f'[INFO] 模型二(趋势中继): {len(m2_stocks)}只')
    print(f'[INFO] 去重合计: {len(all_stocks)}只')
    print(f'\n=== 补涨标的 ===')
    for s in all_stocks:
        q = s.get('quality', '-')
        rt = s.get('reason_type', '')
        rt_str = f' [{rt}]' if rt else ''
        print(f'  [{s["mainline"]}] {s["code_short"]} {s["name"]} +{s["change"]}% {s["model_label"]} {s["note"]} 量比{s["vol_ratio"]} 质量{q}{rt_str}')


if __name__ == '__main__':
    main()

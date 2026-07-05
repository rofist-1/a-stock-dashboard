# -*- coding: utf-8 -*-
import pandas as pd
import json, os

desktop = r'C:\Users\Rofis\Desktop'
sector_map_path = os.path.join(desktop, '百日新高系统', 'sector_map.json')
stock_list_path = os.path.join(desktop, '百日新高系统', 'stock_list.json')

# 1. 找文件
files = os.listdir(desktop)
xlsx = [f for f in files if '20260620' in f and f.endswith('.xlsx')]
if not xlsx:
    print('找不到全部A股20260620.xlsx')
    exit()
path = os.path.join(desktop, xlsx[0])

# 2. 读取
df = pd.read_excel(path)
cols = [c.strip() for c in df.columns]

# 列名映射（通达信格式）
col_map = {
    '代码': cols[0], '名称': cols[1], '涨幅%': cols[2], '最新价': cols[3],
    '成交额': cols[5], '涨速%': cols[7], '10日涨幅%': cols[8],
    '距60日线%': cols[10], '量比': cols[11], '流通市值': cols[12],
    '换手率Z': cols[13], '20日涨幅%': cols[14],
}
inv = {v: k for k, v in col_map.items()}

# 3. 加载sector_map
with open(sector_map_path, 'r', encoding='utf-8') as f:
    sector_map = json.load(f)

# 4. 定义芯片和机器人的相关行业关键词
CHIP_KEYWORDS = ['半导体', '芯片', '集成电路', '元器件', '电子元件', '电子器件', '光学', '光电子',
                 'PCB', '印制电路', '封装', '封测', '材料', '硅片', '光刻', '靶材', '电子化学品']
ROBOT_KEYWORDS = ['机器人', '自动化', '工业母机', '机床', '减速器', '伺服', '传感器',
                  '机器视觉', '数控', '机械', '智能装备', '高端装备', '人形机器人',
                  '滚珠丝杠', '轴承', '液压', '气动']

def match_sector(code, name):
    """判断股票是否属于芯片或机器人主线"""
    code_clean = str(code).strip()
    if not code_clean.startswith('6') and not code_clean.startswith('0') and not code_clean.startswith('3'):
        if code_clean.startswith('68'):
            code_full = code_clean + '.SH'
    name_lower = str(name).lower()
    
    # 补齐后缀
    if code_clean.startswith('6') or code_clean.startswith('68'):
        code_full = code_clean + '.SH'
    elif code_clean.startswith('0') or code_clean.startswith('3'):
        code_full = code_clean + '.SZ'
    elif code_clean.startswith('8'):
        code_full = code_clean + '.BJ'
    else:
        code_full = code_clean
    
    sector = sector_map.get(code_full, sector_map.get(code_clean, ''))
    if not sector:
        sector = sector_map.get(code_clean + '.SH', sector_map.get(code_clean + '.SZ', ''))
    
    is_chip = False
    is_robot = False
    
    if sector:
        s = sector.lower()
        for kw in CHIP_KEYWORDS:
            if kw.lower() in s:
                is_chip = True
                break
        for kw in ROBOT_KEYWORDS:
            if kw.lower() in s:
                is_robot = True
                break
    
    # 名称辅助匹配
    n = str(name).lower()
    chip_names = ['芯片', '半导体', '晶圆', '封测', '光刻', '靶材', '硅片']
    robot_names = ['机器人', '减速器', '伺服', '数控', '机器视觉']
    for kw in chip_names:
        if kw in n:
            is_chip = True
    for kw in robot_names:
        if kw in n:
            is_robot = True
    
    return is_chip, is_robot, sector if sector else '未知'

# 5. 筛选
results_chip_m1 = []  # 芯片-模型一
results_chip_m2 = []  # 芯片-模型二
results_robot_m1 = [] # 机器人-模型一
results_robot_m2 = [] # 机器人-模型二

for _, row in df.iterrows():
    try:
        code = str(row[cols[0]]).strip()
        name = str(row[cols[1]]).strip()
        chg_str = str(row[cols[2]]).strip()
        ma60_str = str(row[cols[10]]).strip() if cols[10] else '0'
        vol_ratio_str = str(row[cols[11]]).strip() if cols[11] else '0'
        close_val = row[cols[3]]
        # 10日涨幅
        chg10 = str(row[cols[8]]).strip() if cols[8] else '0'
        # 成交额
        amount = str(row[cols[5]]).strip() if cols[5] else '0'
    except:
        continue
    
    # 解析数值
    try:
        chg = float(chg_str.replace('%', '')) if chg_str not in ('--', '-', '', 'NaN', 'nan') else None
    except:
        chg = None
    try:
        ma60_dist = float(ma60_str.replace('%', '')) if ma60_str not in ('--', '-', '', 'NaN', 'nan') else None
    except:
        ma60_dist = None
    try:
        vr = float(vol_ratio_str) if vol_ratio_str not in ('--', '-', '', 'NaN', 'nan') else None
    except:
        vr = None
    try:
        chg10_val = float(chg10.replace('%', '')) if chg10 not in ('--', '-', '', 'NaN', 'nan') else None
    except:
        chg10_val = None
    try:
        amount_val = float(amount) if amount not in ('--', '-', '', 'NaN', 'nan') else None
    except:
        amount_val = None
    
    # 过滤：不满足涨幅>5%或涨停
    if chg is None or chg < 5:
        continue
    
    # 判断主线
    is_chip, is_robot, sector_name = match_sector(code, name)
    if not is_chip and not is_robot:
        continue
    
    # 解析距60日线
    if ma60_dist is None:
        continue
    
    # 模型一：底部补涨启动型
    # 股价在60日线附近（刚站上 -3% ~ +5%），放量（量比>1 或 成交额明显）
    if -3 <= ma60_dist <= 5:
        if vr is not None and vr >= 0.8:
            desc = f'股价距60日线{ma60_dist:+.1f}%，放量{vr:.1f}倍大阳线+{chg:.1f}%'
            if ma60_dist >= 0:
                desc += '，刚站上60日线启动'
            else:
                desc += '，回踩60日线后反弹'
            item = (code, name, chg, ma60_dist, vr)
            if is_chip:
                results_chip_m1.append((item, desc))
            if is_robot:
                results_robot_m1.append((item, desc))
    
    # 模型二：趋势中继突破型
    # 股价在60日线上方运行（>5%），10日涨幅不太大（<30%），放量突破
    if ma60_dist > 5 and (chg10_val is None or chg10_val < 30):
        if vr is not None and vr >= 0.8:
            desc = f'股价在60日线上方{ma60_dist:+.1f}%，今日放量{vr:.1f}倍大阳线+{chg:.1f}%'
            if chg >= 9.5:
                desc += '，涨停突破'
            else:
                desc += '，趋势加速'
            item = (code, name, chg, ma60_dist, vr)
            if is_chip:
                results_chip_m2.append((item, desc))
            if is_robot:
                results_robot_m2.append((item, desc))

# 6. 输出结果
print('=' * 70)
print('                A股主线补涨/趋势启动筛选报告')
print(f'                数据日期：2026-06-20')
print('=' * 70)

def print_section(title, results, model_label):
    print(f'\n{"─" * 50}')
    print(f'  {title}')
    print(f'  {model_label}')
    print(f'  {"─" * 50}')
    if not results:
        print('  无符合条件的股票')
        return
    for (code, name, chg, ma60, vr), desc in results:
        chg_str = f'+{chg:.1f}%' if chg >= 0 else f'{chg:.1f}%'
        print(f'  {code} {name} {chg_str}')
        print(f'    → {desc}')
    print(f'  共 {len(results)} 只')

print_section('芯片主线（半导体/元器件/材料等）— 模型一：底部补涨启动型', results_chip_m1, '')
print_section('芯片主线 — 模型二：趋势中继突破型', results_chip_m2, '')
print_section('机器人主线（机器人/自动化/数控等）— 模型一：底部补涨启动型', results_robot_m1, '')
print_section('机器人主线 — 模型二：趋势中继突破型', results_robot_m2, '')

print(f'\n{"=" * 70}')
print(f'筛选范围：{len(df)} 只A股')
print(f'涨幅>5%：{len([1 for _, r in df.iterrows() if str(r[cols[2]]).strip() not in ("--", "-", "", "NaN", "nan") and float(str(r[cols[2]]).replace("%", "").strip()) >= 5])} 只')
total = len(results_chip_m1) + len(results_chip_m2) + len(results_robot_m1) + len(results_robot_m2)
print(f'命中主线补涨/突破信号：{total} 只')
print('免责声明：本筛选仅提供技术形态参考，不构成投资建议。')

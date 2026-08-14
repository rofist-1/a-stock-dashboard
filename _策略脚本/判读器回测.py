# -*- coding: utf-8 -*-
"""
判读器信号有效性回测 v1
========================
目标: 验证判读器"模式判定"对次日市场质量的预测力(择时鉴别力)
  - 判"主升"日的次日, 是否真的比判"轮动"日的次日市场更好?
  - 若判读器有鉴别力, 则主升日次日质量显著 > 轮动日次日质量

编译口径(与判读器 v1.4/V3.6 一致):
  源① s1题材连续登顶天数 >=5天  → 过
  源② 单题材百日新高占比 双口径并列(任一即过):
       A. 一级行业占比 = s1Total / newHigh >= 25%
       B. 最大细分占比 = max(s1b1New,s1b2New) / newHigh >= 20%
  (8/13 实测复核: 46/106=43.4% 过A, 33/106=31.1% 过B -> 双口径皆过, 与手册记录一致)

数据缺口声明(重要):
  源③ 大市值龙头量产新高  -- 看板JSON无个股字段, 无法编译
  源④ 高度板>3板且主线贡献 -- 看板JSON无高度板字段(chain是连板家数非高度), 无法编译
  → 本版仅编译 ①+② 两个可精确计算源, 判定为"主升候选/轮动"
  → ③④对8/14判读的实际影响: 均为"不过"(龙头破位/最高板非主线), 与①②判定一致方向

次日市场质量口径(沿用 backtest.py estimate_return):
  quality = (newHigh-newLow)/(newHigh+newLow)*0.6 + (limitUp-limitDown)/(limitUp+limitDown)*0.4
  正值=次日偏强, 负值=次日偏弱

防未来函数: 用T日数据判定 -> 观察T+1日质量(实际执行日)

用法: python 判读器回测.py
输出: 控制台报告 + 判读器回测_明细.csv
"""
import json
import csv
import sys
import io
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATA_FILE = 'a股波段看板_2026-08-13.json'


def load_data():
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)


def is_data_gap(d):
    """标记看板数据缺失日(无s1字段 或 newHigh=0)"""
    s1 = str(d.get('s1Name', '') or '').strip()
    if not s1:
        return True
    if d.get('newHigh', 0) <= 0:
        return True
    return False


def s1_streak(data, idx):
    """源①: s1题材连续登顶天数(含当日)"""
    name = str(data[idx].get('s1Name', '') or '').strip()
    if not name:
        return 0
    cnt = 0
    for i in range(idx, -1, -1):
        n = str(data[i].get('s1Name', '') or '').strip()
        if n == name:
            cnt += 1
        else:
            break
    return cnt


def judge_double_ratio(d):
    """源②: 单题材百日新高占比, 双口径并列(任一过即过)
    返回 (是否过, A占比, B占比, A过否, B过否)"""
    nh = d.get('newHigh', 0)
    if nh <= 0:
        return (False, 0.0, 0.0, False, False)
    s1_total = d.get('s1Total', 0) or 0
    b1 = d.get('s1b1New', 0) or 0
    b2 = d.get('s1b2New', 0) or 0
    ratio_a = s1_total / nh
    ratio_b = max(b1, b2) / nh
    pass_a = ratio_a >= 0.25
    pass_b = ratio_b >= 0.20
    return (pass_a or pass_b, ratio_a, ratio_b, pass_a, pass_b)


def judge(data, idx):
    """判读器编译(①+②), 返回判定详情"""
    d = data[idx]
    if is_data_gap(d):
        return {'gap': True}

    s1 = str(d.get('s1Name', '') or '').strip()
    streak = s1_streak(data, idx)
    src1 = streak >= 5

    src2, ratio_a, ratio_b, pa, pb = judge_double_ratio(d)

    # 综合: 任一源不过 -> 轮动; 全过 -> 主升候选
    main_up = src1 and src2

    return {
        'gap': False,
        'date': d['date'],
        's1': s1,
        'streak': streak,
        'src1': src1,
        'ratio_a': ratio_a,
        'ratio_b': ratio_b,
        'src2': src2,
        'mode': '主升候选' if main_up else '轮动',
        'lu': d.get('limitUp', 0),
        'ld': d.get('limitDown', 0),
        'bomb': d.get('bomb', 0),
        'chain': d.get('chain', 0),
        'nh': d.get('newHigh', 0),
        'nl': d.get('newLow', 0),
        'vol': d.get('volume', 0),
    }


def next_quality(data, idx):
    """T+1日市场质量(实际执行日)"""
    if idx + 1 >= len(data):
        return None
    d = data[idx + 1]
    if is_data_gap(d):
        return None
    nh, nl = d.get('newHigh', 0), d.get('newLow', 0)
    lu, ld = d.get('limitUp', 0), d.get('limitDown', 0)
    breadth = (nh - nl) / max(nh + nl, 1)
    sentiment = (lu - ld) / max(lu + ld, 1)
    q = breadth * 0.6 + sentiment * 0.4
    return {
        'date': d['date'],
        'quality': q,
        'lu': lu, 'ld': ld, 'nh': nh, 'nl': nl,
        'vol': d.get('volume', 0),
        'chain': d.get('chain', 0),
    }


def main():
    data = load_data()
    n = len(data)
    print('=' * 70)
    print('  判读器信号有效性回测 v1  (源①+源②编译, ③④缺口标注)')
    print('=' * 70)
    print(f'  数据范围: {data[0]["date"]} ~ {data[-1]["date"]} 共{n}个交易日')
    print(f'  判定口径: 源①s1登顶>=5天 且 源②(一级>=25%或细分>=20%) -> 主升候选, 否则轮动')
    print(f'  验证方式: T日判定 -> T+1日市场质量(实际执行日), 防未来函数')
    print(f'  数据缺口: 源③龙头新高/源④高度板 看板JSON无字段, 本版不参与')

    rows = []
    for i in range(n):
        j = judge(data, i)
        q = next_quality(data, i)
        if not j.get('gap', False):
            rows.append({**j, 'next': q})

    gaps = sum(1 for i in range(n) if judge(data, i).get('gap'))
    print(f'  剔除数据缺口日: {gaps}天 (2月中/6月末无主线字段或新高=0)')
    print(f'  有效样本: {len(rows)}天')

    # 分组统计
    main_grp = [r for r in rows if r['mode'] == '主升候选' and r['next']]
    rot_grp = [r for r in rows if r['mode'] == '轮动' and r['next']]

    print()
    print('─' * 70)
    print('  【信号有效性: 判定 -> 次日质量】')
    print('─' * 70)

    def stats(grp):
        qs = [r['next']['quality'] for r in grp]
        if not qs:
            return None
        avg = sum(qs) / len(qs)
        sorted_qs = sorted(qs)
        mid = sorted_qs[len(qs) // 2]
        pos = sum(1 for q in qs if q > 0) / len(qs)
        return {'n': len(qs), 'avg': avg, 'mid': mid, 'pos': pos, 'qs': qs}

    ms = stats(main_grp)
    rs = stats(rot_grp)
    all_qs = [r['next']['quality'] for r in rows if r['next']]

    hdr = f"{'判定':<8}{'天数':<5}{'次日均质':<10}{'中位':<8}{'次日为正率':<10}{'次日涨停均值':<12}{'次日宽度(涨-跌)/总':<12}"
    print(f"  {hdr}")
    print(f"  {'─' * 78}")

    def nxt_extra(grp):
        qs = [r['next'] for r in grp]
        avg_lu = sum(x['lu'] for x in qs) / len(qs)
        avg_wd = sum((x['nh'] - x['nl']) / max(x['nh'] + x['nl'], 1) for x in qs) / len(qs)
        return avg_lu, avg_wd

    if ms:
        a, w = nxt_extra(main_grp)
        print(f"  {'主升候选':<8}{ms['n']:<5}{ms['avg']:>+8.3f}{ms['mid']:>+8.3f}{ms['pos']:>9.1%}{a:>12.1f}{w:>12.3f}")
    if rs:
        a, w = nxt_extra(rot_grp)
        print(f"  {'轮动':<8}{rs['n']:<5}{rs['avg']:>+8.3f}{rs['mid']:>+8.3f}{rs['pos']:>9.1%}{a:>12.1f}{w:>12.3f}")
    if all_qs:
        avg_all = sum(all_qs) / len(all_qs)
        print(f"  {'全样本':<8}{len(all_qs):<5}{avg_all:>+8.3f}")

    print()
    diff = (ms['avg'] - rs['avg']) if ms and rs else 0
    print(f"  区分度: 主升候选次日均质 {ms['avg']:+.3f} vs 轮动次日均质 {rs['avg']:+.3f}")
    print(f"  差值: {diff:+.3f}  ", end='')
    if diff > 0.15:
        print('✔ 判读器有强择时鉴别力 (主升日次日显著更好)')
    elif diff > 0.05:
        print('✓ 判读器有一定鉴别力')
    else:
        print('⚠ 判读器区分力较弱或不足')

    # 主升候选明细
    print()
    print('  【主升候选日 及其 次日实际质量】')
    print(f"  {'判定日':<12}{'s1主线':<10}{'登顶':<4}{'A占比':<7}{'B占比':<7}{'模式':<8}{'次日日期':<12}{'次日质量':<9}{'次涨停':<6}{'次跌停':<6}")
    print(f"  {'─' * 90}")
    for r in main_grp:
        nq = r['next']
        print(f"  {r['date']:<12}{r['s1']:<10}{r['streak']:<4}{r['ratio_a']:>6.1%}{r['ratio_b']:>7.1%}{r['mode']:<8}{nq['date']:<12}{nq['quality']:>+8.3f}{nq['lu']:<6}{nq['ld']:<6}")

    # 轮动日明细(最近15条)
    print()
    print('  【轮动日 及其 次日实际质量 (最近15条)】')
    print(f"  {'判定日':<12}{'s1主线':<10}{'登顶':<4}{'A占比':<7}{'B占比':<7}{'模式':<8}{'次日日期':<12}{'次日质量':<9}{'次涨停':<6}{'次跌停':<6}")
    print(f"  {'─' * 90}")
    for r in rot_grp[-15:]:
        nq = r['next']
        print(f"  {r['date']:<12}{r['s1']:<10}{r['streak']:<4}{r['ratio_a']:>6.1%}{r['ratio_b']:>7.1%}{r['mode']:<8}{nq['date']:<12}{nq['quality']:>+8.3f}{nq['lu']:<6}{nq['ld']:<6}")

    # 近30天模式序列
    print()
    print('  【模式序列 (最近30个有效日)】')
    seq = rows[-30:]
    for r in seq:
        bar = '主升' if r['mode'] == '主升候选' else '轮动'
        nq = r['next']
        qstr = f"{nq['quality']:+.2f}" if nq else 'N/A'
        flag = ' ★' if r['mode'] == '主升候选' and nq and nq['quality'] > 0 else ''
        print(f"  {r['date']} {r['s1']:<8} {bar}  -> 次日{qstr}{flag}")

    # 导出
    with open('判读器回测_明细.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['判定日', 's1主线', '登顶天数', '源①', 'A占比', 'B占比', '源②', '判定模式',
                    '当日涨停', '当日跌停', '次日日期', '次日质量', '次日涨停', '次日跌停', '次日新高', '次日新低'])
        for r in rows:
            nq = r['next']
            w.writerow([r['date'], r['s1'], r['streak'], '过' if r['src1'] else '不过',
                        f"{r['ratio_a']:.1%}", f"{r['ratio_b']:.1%}", '过' if r['src2'] else '不过',
                        r['mode'], r['lu'], r['ld'],
                        nq['date'] if nq else '', f"{nq['quality']:.3f}" if nq else '',
                        nq['lu'] if nq else '', nq['ld'] if nq else '',
                        nq['nh'] if nq else '', nq['nl'] if nq else ''])
    print()
    print(f"  明细已导出: 判读器回测_明细.csv")


if __name__ == '__main__':
    main()

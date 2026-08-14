# -*- coding: utf-8 -*-
"""
判读器信号有效性回测 v2 (环境闸门 + 主线延续口径)
==================================================
v1 结论: 用"全市场次日质量"验证"主线强度判读"= 标尺错位, 方向反了
v2 修正(用户确认的四点方法论):
  1. 新增【全市场环境闸门】: 判主升前先查大盘健康度, 过滤7月那种
     "医药主线连续登顶但全市场新低暴增"的假主升
  2. 验证口径切换到【主线自身延续强度】: 用次日 s1Name/s1Total/s1New
     度量"主线是否续强/延续", 不再用全市场次日表现

闸门定义(两档, 都输出做对照):
  - 宽松闸门: 当日 newHigh > newLow (百日新高主导, 大盘结构向上)
  - 严格闸门: newHigh > newLow 且 limitDown <= 15 (新高主导 + 跌停不拥挤)

主线延续强度(T+1, 判主升日次日):
  - 同名延续: T+1 的 s1Name == T 的 s1Name
  - 池子续扩: s1Total(T+1) - s1Total(T) > 0  (主线百日新高池仍在扩容)
  - 新增续强: s1New(T+1) >= 1  (次日主线仍有新票创百日新高)

预期(判读器有鉴别力时的表现):
  主升日次日: 同名率高、池子续扩比例高、新增续强比例高
  轮动日次日: 主线换帅(同名率低), 池子不再扩张

用法: python 判读器回测_v2.py
输出: 控制台报告 + 判读器回测_v2_明细.csv
"""
import json
import csv
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATA_FILE = 'a股波段看板_2026-08-13.json'


def load_data():
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)


def is_data_gap(d):
    """数据缺口日: 无s1字段 或 newHigh=0"""
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
    """源②: 单题材百日新高占比, 双口径并列(任一过即过)"""
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


def env_gate(d):
    """全市场环境闸门, 返回(宽松过, 严格过, nh, nl, ld)"""
    nh = d.get('newHigh', 0)
    nl = d.get('newLow', 0)
    ld = d.get('limitDown', 0)
    loose = nh > nl
    strict = loose and ld <= 15
    return loose, strict, nh, nl, ld


def judge(data, idx):
    """判读器编译(①+②+环境闸门)"""
    d = data[idx]
    if is_data_gap(d):
        return {'gap': True}

    s1 = str(d.get('s1Name', '') or '').strip()
    streak = s1_streak(data, idx)
    src1 = streak >= 5

    src2, ratio_a, ratio_b, pa, pb = judge_double_ratio(d)
    loose, strict, nh, nl, ld = env_gate(d)

    # 四源 + 闸门: 全过(严格) -> 主升; 过宽松闸门 -> 主升候选(宽松); 否则轮动
    src_ok = src1 and src2
    mode_strict = '主升(严格)' if (src_ok and strict) else None
    if mode_strict:
        mode = mode_strict
    elif src_ok and loose:
        mode = '主升(宽松)'
    elif src_ok and not loose:
        mode = '主升-闸门否决'
    else:
        mode = '轮动'

    return {
        'gap': False,
        'date': d['date'],
        's1': s1,
        'streak': streak,
        'src1': src1,
        'ratio_a': ratio_a,
        'ratio_b': ratio_b,
        'src2': src2,
        'gate_loose': loose,
        'gate_strict': strict,
        'nh': nh, 'nl': nl, 'ld': ld,
        'mode': mode,
        'lu': d.get('limitUp', 0),
        'bomb': d.get('bomb', 0),
        'chain': d.get('chain', 0),
        's1_total': d.get('s1Total', 0),
        's1_new': d.get('s1New', 0),
    }


def next_mainline(data, idx):
    """T+1主线延续信息"""
    if idx + 1 >= len(data):
        return None
    nxt = data[idx + 1]
    if is_data_gap(nxt):
        return None
    cur = data[idx]
    same = str(nxt.get('s1Name', '') or '').strip() == str(cur.get('s1Name', '') or '').strip()
    pool_prev = cur.get('s1Total', 0) or 0
    pool_next = nxt.get('s1Total', 0) or 0
    s1new_prev = cur.get('s1New', 0) or 0
    s1new_next = nxt.get('s1New', 0) or 0
    return {
        'next_date': nxt['date'],
        'next_s1': str(nxt.get('s1Name', '') or '').strip(),
        'same': same,
        'pool_prev': pool_prev,
        'pool_next': pool_next,
        'pool_chg': pool_next - pool_prev,
        's1new_prev': s1new_prev,
        's1new_next': s1new_next,
        'next_lu': nxt.get('limitUp', 0),
        'next_nh': nxt.get('newHigh', 0),
        'next_nl': nxt.get('newLow', 0),
    }


def cont_stats(grp):
    """主线延续统计"""
    grp = [r for r in grp if r['next']]
    if not grp:
        return None
    n = len(grp)
    same_n = sum(1 for r in grp if r['next']['same'])
    pool_grow = sum(1 for r in grp if r['next']['pool_chg'] > 0)
    new_cont = sum(1 for r in grp if r['next']['s1new_next'] >= 1)
    avg_pool_chg = sum(r['next']['pool_chg'] for r in grp) / n
    avg_s1new_next = sum(r['next']['s1new_next'] for r in grp) / n
    return {
        'n': n,
        'same': same_n / n,
        'pool_grow': pool_grow / n,
        'new_cont': new_cont / n,
        'avg_pool_chg': avg_pool_chg,
        'avg_s1new_next': avg_s1new_next,
        'grp': grp,
    }


def main():
    data = load_data()
    n = len(data)
    print('=' * 78)
    print('  判读器信号有效性回测 v2  (源①+源②+环境闸门 / 主线延续口径)')
    print('=' * 78)
    print(f'  数据范围: {data[0]["date"]} ~ {data[-1]["date"]} 共{n}个交易日')
    print(f'  判读规则: 源①登顶>=5天 且 源②(一级>=25%或细分>=20%) -> 源过')
    print(f'            源过 + 宽松闸门(newHigh>newLow) -> 主升(宽松)')
    print(f'            源过 + 严格闸门(+limitDown<=15) -> 主升(严格)')
    print(f'  验证口径: T日判定 -> T+1主线延续(同名率/池子续扩/新增续强)')

    rows = []
    for i in range(n):
        j = judge(data, i)
        if not j.get('gap', False):
            rows.append({**j, 'next': next_mainline(data, i)})

    gaps = n - len(rows)
    print(f'  剔除数据缺口: {gaps}天 | 有效样本: {len(rows)}天')

    # 分组: 主升(严格+宽松) / 闸门否决 / 轮动
    main_strict = [r for r in rows if r['mode'] == '主升(严格)']
    main_loose = [r for r in rows if r['mode'] == '主升(宽松)']
    gate_blocked = [r for r in rows if r['mode'] == '主升-闸门否决']
    rot = [r for r in rows if r['mode'] == '轮动']

    # 预定义分组
    groups = [
        ('主升(严格)', main_strict),
        ('主升(宽松)', main_loose),
        ('主升合计', main_strict + main_loose),
        ('闸门否决(假主升)', gate_blocked),
        ('轮动', rot),
    ]

    print()
    print('─' * 78)
    print('  【样本分布: 判定分档】')
    print('─' * 78)
    print(f"  {'分档':<16}{'天数':<6}{'次日有数据':<8}{'次日同名延续':<10}{'次日池子续扩':<10}{'次日新增续强':<10}")
    print(f"  {'─' * 66}")
    for name, grp in groups:
        cs = cont_stats(grp)
        if cs:
            print(f"  {name:<16}{len(grp):<6}{cs['n']:<8}{cs['same']:>9.1%}{cs['pool_grow']:>10.1%}{cs['new_cont']:>10.1%}")
        else:
            print(f"  {name:<16}{len(grp):<6}{0:<8}{'-':<10}{'-':<10}{'-':<10}")

    print()
    print('  【区分度: 主升 vs 轮动 (主线延续口径)】')
    m_cs = cont_stats(main_strict + main_loose)
    r_cs = cont_stats(rot)
    if m_cs and r_cs:
        print(f"  主升{len(main_strict)+len(main_loose)}天(含严格{len(main_strict)}): "
              f"同名延续{m_cs['same']:.0%} | 池子续扩{m_cs['pool_grow']:.0%} | 新增续强{m_cs['new_cont']:.0%} | "
              f"平均池变化{m_cs['avg_pool_chg']:+.1f} | 次日均新增{m_cs['avg_s1new_next']:.1f}")
        print(f"  轮动{len(rot)}天: "
              f"同名延续{r_cs['same']:.0%} | 池子续扩{r_cs['pool_grow']:.0%} | 新增续强{r_cs['new_cont']:.0%} | "
              f"平均池变化{r_cs['avg_pool_chg']:+.1f} | 次日均新增{r_cs['avg_s1new_next']:.1f}")
        d_same = m_cs['same'] - r_cs['same']
        d_grow = m_cs['pool_grow'] - r_cs['pool_grow']
        print(f"  差值: 同名{'+' if d_same>=0 else ''}{d_same:.0%} | 池续扩{'+' if d_grow>=0 else ''}{d_grow:.0%}")
        verdict = '✔ 判读器对主线延续有鉴别力' if (d_same > 0.1 and d_grow > 0.1) else \
                  '✓ 判读器有一定鉴别力(需看明细)' if (d_same > 0 or d_grow > 0) else \
                  '⚠ 判读器对主线延续无明显鉴别力'
        print(f"  结论: {verdict}")

    # 闸门效果
    print()
    print('─' * 78)
    print('  【环境闸门效果: 主升候选中被闸门否决的日子】')
    print('─' * 78)
    print(f"  {'判定日':<12}{'s1主线':<8}{'登顶':<4}{'A占比':<7}{'B占比':<7}{'newHigh':<8}{'newLow':<7}{'跌停':<5}{'判决'}")
    print(f"  {'─' * 72}")
    for r in gate_blocked:
        print(f"  {r['date']:<12}{r['s1']:<8}{r['streak']:<4}{r['ratio_a']:>6.1%}{r['ratio_b']:>7.1%}"
              f"{r['nh']:<8}{r['nl']:<7}{r['ld']:<5}主升-闸门否决")

    # 主升明细
    print()
    print('─' * 78)
    print('  【主升日 及其 次日主线延续明细】')
    print('─' * 78)
    print(f"  {'判定日':<12}{'s1':<8}{'登顶':<4}{'A%':<7}{'B%':<7}{'闸门':<6}{'次日':<12}{'次日s1':<8}{'同名':<4}{'池':<5}{'池变':<6}{'新增':<6}")
    print(f"  {'─' * 96}")
    for r in main_strict + main_loose:
        nq = r['next']
        if nq:
            print(f"  {r['date']:<12}{r['s1']:<8}{r['streak']:<4}{r['ratio_a']:>6.1%}{r['ratio_b']:>7.1%}"
                  f"{'严' if r['gate_strict'] else '松':<6}{nq['next_date']:<12}{nq['next_s1']:<8}"
                  f"{'√' if nq['same'] else '✗':<4}{nq['pool_next']:<5}{nq['pool_chg']:>+5}{nq['s1new_next']:<6}")

    # 轮动日主线延续(最近10条)
    print()
    print('  【轮动日 次日主线延续 (最近10条)】')
    print(f"  {'判定日':<12}{'s1':<8}{'登顶':<4}{'A%':<7}{'B%':<7}{'次日':<12}{'次日s1':<8}{'同名':<4}{'池变':<6}{'次日新增':<7}")
    print(f"  {'─' * 78}")
    for r in rot[-10:]:
        nq = r['next']
        if nq:
            print(f"  {r['date']:<12}{r['s1']:<8}{r['streak']:<4}{r['ratio_a']:>6.1%}{r['ratio_b']:>7.1%}"
                  f"{nq['next_date']:<12}{nq['next_s1']:<8}{'√' if nq['same'] else '✗':<4}{nq['pool_chg']:>+5}{nq['s1new_next']:<7}")

    # 闸门否决日 次日实际表现(看假主升是否真危险)
    print()
    print('  【闸门否决日 次日主线状态 (验证假主升确实该拦)】')
    for r in gate_blocked:
        nq = r['next']
        if nq:
            verdict = '延续' if nq['same'] else '换帅'
            print(f"  {r['date']} {r['s1']}({r['streak']}天/占比{r['ratio_a']:.0%}) 闸门否决"
                  f" -> 次日{nq['next_date']} {nq['next_s1']} {verdict} 池变{nq['pool_chg']:+d} 新低{nq['next_nl']}")

    # 导出
    with open('判读器回测_v2_明细.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['判定日', 's1', '登顶', '源①', 'A占比', 'B占比', '源②', '宽松闸门', '严格闸门',
                    '判决', '当日涨停', '当日新高', '当日新低', '当日跌停',
                    '次日日期', '次日s1', '同名延续', '次日池', '池变化', '次日新增', '次日涨停', '次日新高', '次日新低'])
        for r in rows:
            nq = r['next']
            w.writerow([r['date'], r['s1'], r['streak'], '过' if r['src1'] else '不过',
                        f"{r['ratio_a']:.1%}", f"{r['ratio_b']:.1%}", '过' if r['src2'] else '不过',
                        '过' if r['gate_loose'] else '否', '过' if r['gate_strict'] else '否',
                        r['mode'], r['lu'], r['nh'], r['nl'], r['ld'],
                        nq['next_date'] if nq else '', nq['next_s1'] if nq else '',
                        '√' if nq and nq['same'] else ('✗' if nq else ''),
                        nq['pool_next'] if nq else '', nq['pool_chg'] if nq else '',
                        nq['s1new_next'] if nq else '', nq['next_lu'] if nq else '',
                        nq['next_nh'] if nq else '', nq['next_nl'] if nq else ''])
    print()
    print(f"  明细已导出: 判读器回测_v2_明细.csv")


if __name__ == '__main__':
    main()

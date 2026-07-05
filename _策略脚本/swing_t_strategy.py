"""
A股波段+做T 量化操作系统
- 波段: 基于市场环境+板块轮动的中线持仓策略
- 做T: 基于日内波动信号的底仓增强策略
数据源: a股波段看板_2026-05-31.json
"""
import json
import math
from collections import defaultdict

with open("a股波段看板_2026-05-31.json", encoding="utf-8") as f:
    raw = json.load(f)

# ════════════════════════════════════════════
# 第一部分: 市场状态评分
# ════════════════════════════════════════════

def market_score(d):
    """综合市场评分 0-100"""
    s = 0
    lu = d["limitUp"]
    ld = d["limitDown"]
    bomb = d["bomb"]
    ch = d["chain"]
    v = d["volume"]
    nh = d["newHigh"]
    nl = d["newLow"]

    # 涨停 (20)
    if lu >= 100: s += 20
    elif lu >= 80: s += 16
    elif lu >= 60: s += 12
    elif lu >= 40: s += 8
    elif lu >= 20: s += 4

    # 跌停 (-20惩罚)
    if ld <= 3: s += 20
    elif ld <= 8: s += 12
    elif ld <= 15: s += 4
    elif ld <= 25: s -= 10
    else: s -= 25

    # 炸板率 (20)
    br = bomb / max(lu, 1)
    if br < 0.2: s += 20
    elif br < 0.3: s += 15
    elif br < 0.4: s += 10
    elif br < 0.5: s += 5
    else: s -= 5

    # 连板 (15)
    if ch >= 20: s += 15
    elif ch >= 12: s += 12
    elif ch >= 8: s += 8
    elif ch >= 5: s += 4

    # 成交额 (15)
    if v >= 35000: s += 15
    elif v >= 30000: s += 12
    elif v >= 25000: s += 8
    elif v >= 20000: s += 5
    elif v >= 15000: s += 2

    # 新高/新低比 (20)
    ratio = nh / max(nl, 1)
    if ratio >= 15: s += 20
    elif ratio >= 8: s += 16
    elif ratio >= 4: s += 12
    elif ratio >= 2: s += 8
    elif ratio >= 1: s += 4
    else: s -= 10

    return max(0, min(100, s))

# ════════════════════════════════════════════
# 第二部分: 做T适用度评分
# ════════════════════════════════════════════

def t_score(d):
    """
    做T环境评分 0-100
    高 = 波动大+流动性好，适合做T降低成本
    """
    lu = d["limitUp"]
    ld = d["limitDown"]
    bomb = d["bomb"]
    ch = d["chain"]
    v = d["volume"]

    # 炸板率 → 波动性 (30分) 炸板率越高，日内波动越大
    br = bomb / max(lu, 1)
    if br >= 0.5: ts = 30      # 剧烈分歧，大波动
    elif br >= 0.35: ts = 25   # 中度分歧
    elif br >= 0.25: ts = 18   # 轻度分歧
    elif br >= 0.15: ts = 10   # 一致
    else: ts = 5                # 高度一致，波动小

    # 成交额 → 流动性 (25分)
    if v >= 30000: ts += 25
    elif v >= 25000: ts += 20
    elif v >= 20000: ts += 15
    elif v >= 15000: ts += 10
    elif v >= 10000: ts += 5

    # 涨跌停差 → 博弈空间 (25分)
    gap = lu - ld
    if gap >= 100: ts += 25
    elif gap >= 60: ts += 20
    elif gap >= 30: ts += 15
    elif gap >= 15: ts += 8
    elif gap >= 0: ts += 4
    else: ts += 0

    # 连板 → 连板太高不利于T，容易缩量加速 (20分)
    if ch <= 5: ts += 20       # 低位，T空间大
    elif ch <= 10: ts += 15     # 适中
    elif ch <= 15: ts += 8      # 偏高，T空间变小
    else: ts += 4               # 高位连板，加速期不宜T

    return max(0, min(100, ts))

# ════════════════════════════════════════════
# 第三部分: 信号引擎
# ════════════════════════════════════════════

def analyze_day(d, prev_sectors=None):
    """单日完整分析"""
    ms = market_score(d)
    ts = t_score(d)
    br = d["bomb"] / max(d["limitUp"], 1)
    nh_nl_ratio = d["newHigh"] / max(d["newLow"], 1)

    # 主线板块提取
    sectors = []
    for prefix in ["s1", "s2", "s3"]:
        name = d.get(f"{prefix}Name", "")
        total = d.get(f"{prefix}Total", 0)
        new = d.get(f"{prefix}New", 0)
        if name and total > 0:
            sectors.append({"name": name, "total": total, "new": new})

    top_sector = sectors[0] if sectors else None

    # ─── 波段信号 ───
    swing_signal = "观望"
    swing_reason = []

    if ms >= 75:
        swing_signal = "重仓持有/加仓"
        swing_reason.append(f"市场极强({ms}分)")
    elif ms >= 60:
        swing_signal = "正常持有"
        swing_reason.append(f"市场偏强({ms}分)")
    elif ms >= 45:
        swing_signal = "减仓"
        swing_reason.append(f"市场转弱({ms}分)")
    else:
        swing_signal = "空仓/清仓"
        swing_reason.append(f"市场弱势({ms}分)")

    if top_sector and top_sector["new"] >= 15:
        swing_reason.append(f"主线{top_sector['name']}扩散(+{top_sector['new']})")
    elif top_sector and top_sector["new"] < 5:
        if ms < 60:
            swing_reason.append(f"主线{top_sector['name']}衰竭(+{top_sector['new']})")

    if d["limitDown"] > 20 and ms < 50:
        swing_signal = "清仓"
        swing_reason.append(f"跌停{d['limitDown']}家恐慌")

    # ─── 做T信号 (低频模式) ───
    # 只在炸板率≥50%的极端分歧日触发，减少手续费损耗
    t_signal = "不做T"
    t_reason = []
    t_direction = ""

    if br >= 0.5 and ts >= 60:
        if level in ("B", "C"):
            t_signal = "做T(分歧日)"
            t_direction = "正T(先买后卖)→ 极端分歧日，深跌低吸"
            t_reason.append(f"炸板率{br:.0%}+环境{level}级")
        elif level in ("S", "A"):
            t_signal = "轻仓T"
            t_direction = "正T(先买后卖)→ 强市分歧，小仓低吸"
            t_reason.append(f"强市分歧{br:.0%}")
        else:
            t_signal = "不做T"
            t_reason.append("D级不操作")
    else:
        t_reason.append(f"炸板率{br:.0%}<50%或无极端分歧")

    return {
        "date": d["date"],
        "ms": ms,
        "ts": ts,
        "limitUp": d["limitUp"],
        "limitDown": d["limitDown"],
        "bomb_rate": round(br * 100, 0),
        "chain": d["chain"],
        "volume": d["volume"],
        "newHigh": d["newHigh"],
        "newLow": d["newLow"],
        "nh_nl_ratio": round(nh_nl_ratio, 1),
        "sectors": sectors,
        "swing_signal": swing_signal,
        "swing_reason": " | ".join(swing_reason),
        "t_signal": t_signal,
        "t_direction": t_direction,
        "t_reason": " | ".join(t_reason),
    }

# ════════════════════════════════════════════
# 第四部分: 执行
# ════════════════════════════════════════════

results = [analyze_day(d) for d in raw]

# 统计
total = len(results)
swing_hold = sum(1 for r in results if "重仓" in r["swing_signal"])
swing_normal = sum(1 for r in results if r["swing_signal"] == "正常持有")
swing_reduce = sum(1 for r in results if r["swing_signal"] == "减仓")
swing_none = sum(1 for r in results if "空仓" in r["swing_signal"] or "清仓" in r["swing_signal"])
t_high = sum(1 for r in results if r["ts"] >= 60)
t_mid = sum(1 for r in results if 40 <= r["ts"] < 60)
t_low = sum(1 for r in results if r["ts"] < 40)

# ════════════════════════════════════════════
# 输出
# ════════════════════════════════════════════

print("=" * 80)
print("  A股波段 + 做T 量化操作系统 v2.0")
print(f"  数据周期: {results[0]['date']} ~ {results[-1]['date']} ({total}个交易日)")
print("=" * 80)

print(f"""
【策略总览】
  波段信号分布:
    重仓持有: {swing_hold}天 ({swing_hold/total*100:.0f}%)
    正常持有: {swing_normal}天 ({swing_normal/total*100:.0f}%)
    减仓阶段: {swing_reduce}天 ({swing_reduce/total*100:.0f}%)
    空仓/清仓: {swing_none}天 ({swing_none/total*100:.0f}%)

  做T信号分布:
    积极做T环境(>=60分): {t_high}天 ({t_high/total*100:.0f}%)
    轻仓做T环境(40-59分): {t_mid}天 ({t_mid/total*100:.0f}%)
    不宜做T环境(<40分): {t_low}天 ({t_low/total*100:.0f}%)

  策略特点:
    - 波段覆盖度(持有+正常): {(swing_hold+swing_normal)/total*100:.0f}%
      说明系统有{(swing_hold+swing_normal)/total*100:.0f}%的时间建议持股
    - 做T覆盖度(积极+轻仓): {(t_high+t_mid)/total*100:.0f}%
      说明系统有{(t_high+t_mid)/total*100:.0f}%的时间适合做T降成本
    - 双重共振(波段持有+积极做T): {sum(1 for r in results if r['swing_signal'] in ('重仓持有/加仓','正常持有') and r['ts']>=60)}天
      这些是最佳操作日: 既可持股享受趋势，又可做T降低成本
""")

# 最近交易日详细信号
print("【最近10个交易日完整信号】")
print(f"  {'日期':<12} {'市分':<4} {'波信':<14} {'T分':<4} {'T信号':<10} {'T方向':<30} {'做T原因':<20}")
print(f"  {'-'*94}")
for r in results[-10:]:
    t_dir_short = r['t_direction'][:28] if r['t_direction'] else "-"
    print(f"  {r['date']:<12} {r['ms']:<4} {r['swing_signal']:<14} {r['ts']:<4} {r['t_signal']:<10} {t_dir_short:<30} {r['t_reason'][:18]}")

print()
print("【做T信号最强日Top10】")
top_t = sorted(results, key=lambda x: -x["ts"])[:10]
print(f"  {'日期':<12} {'T分':<4} {'市分':<4} {'炸板率':<8} {'涨跌停差':<10} {'波段信号':<14}")
print(f"  {'-'*52}")
for r in top_t:
    g = r['limitUp'] - r['limitDown']
    print(f"  {r['date']:<12} {r['ts']:<4} {r['ms']:<4} {r['bomb_rate']:<8} {g:<10} {r['swing_signal']:<14}")

print()
print("【波段持仓最佳日Top10】")
top_swing = sorted(results, key=lambda x: -x["ms"])[:10]
print(f"  {'日期':<12} {'市分':<4} {'涨停':<6} {'连板':<4} {'新/新比':<8} {'T分':<4} {'T信号':<10}")
print(f"  {'-'*52}")
for r in top_swing:
    print(f"  {r['date']:<12} {r['ms']:<4} {r['limitUp']:<6} {r['chain']:<4} {r['nh_nl_ratio']:<8} {r['ts']:<4} {r['t_signal']:<10}")

# ════════════════════════════════════════════
# 操作手册
# ════════════════════════════════════════════

print(f"""
{'='*80}
  波段 + 做T 联合操作手册
{'='*80}

┌──────────────┬──────────────┬──────────────────────┬──────────────────────────────┐
│ 市场评分      │ 波段操作      │ 做T策略               │ 组合策略                       │
├──────────────┼──────────────┼──────────────────────┼──────────────────────────────┤
│ S级 (≥75)    │ 满仓持有+加仓 │ 谨慎做T(怕卖飞)        │ 重仓不动，只做极小量倒T          │
│ A级 (60-74)  │ 正常持有      │ 积极双向T             │ 7成底仓+3成做T仓位             │
│ B级 (45-59)  │ 减仓/持有     │ 正T为主               │ 5成底仓，盘中低吸做T            │
│ C级 (30-44)  │ 轻仓防守     │ 只能做正T(低吸)       │ 3成底仓，深跌才T                │
│ D级 (<30)    │ 空仓         │ 不做T                 │ 不操作                        │
└──────────────┴──────────────┴──────────────────────┴──────────────────────────────┘

【做T方向判断规则】
  做T操作        │ 适用条件                                    │ 操作方式
  ─────────────┼────────────────────────────────────────────┼────────────────────────
  正T(先买后卖)  │ 炸板率≥35% + 环境B级以下 → 分歧日低吸        │ 早盘杀跌买→尾盘拉回卖
                │ 板块新增数骤降但环境不差 → 龙头首阴低吸       │
  倒T(先卖后买)  │ 炸板率<20% + 连板≥10 → 一致加速日          │ 开盘冲高卖→尾盘回落接
                │ 连板≥15 → 加速末期限，高抛防断板             │
  双向T         │ 炸板率25-40% + 成交额≥25000 → 充分博弈      │ 先卖后买/先买后卖均可

【做T仓位管理】
  做T环境        │ 做T仓位(占底仓比例)  │ 单笔利润目标  │ 止损
  ─────────────┼──────────────────┼───────────┼──────────
  积极(≥60)     │ 30-50%             │ 1.5-3%    │ 0.5%
  轻仓(40-59)   │ 15-25%             │ 1-2%      │ 0.3%
  不宜(<40)     │ 0%                 │ -         │ -

【风险控制铁律】
  1. 总仓位 = 波段仓位 + 做T仓位 ≤ 100%
  2. 做T仓位收盘前必须平掉(不留过夜)
  3. 跌停>20家时,停止所有做T操作
  4. 当日T亏损超过0.5%立即停止,明日再战
""")

# ════════════════════════════════════════════
# 保存为CSV供进一步分析
# ════════════════════════════════════════════
import csv

csv_path = "operate_signals.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    f.write("\ufeff")
    w = csv.writer(f)
    w.writerow(["日期","市场评分","等级","波段信号","做T评分","做T信号","做T方向","涨停","跌停","炸板率%","连板","成交额","新高","新低","新高/新低比","主线板块","板块新增"])
    for r in results:
        level = "S" if r["ms"] >= 75 else "A" if r["ms"] >= 60 else "B" if r["ms"] >= 45 else "C" if r["ms"] >= 30 else "D"
        sec_name = r["sectors"][0]["name"] if r["sectors"] else ""
        sec_new = r["sectors"][0]["new"] if r["sectors"] else 0
        w.writerow([r["date"], r["ms"], level, r["swing_signal"], r["ts"], r["t_signal"],
                    r["t_direction"], r["limitUp"], r["limitDown"], r["bomb_rate"], r["chain"],
                    r["volume"], r["newHigh"], r["newLow"], r["nh_nl_ratio"], sec_name, sec_new])

print(f"详细信号已导出至: {csv_path}")
